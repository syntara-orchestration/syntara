import { Octokit } from '@octokit/rest';
import { graphql } from '@octokit/graphql';
import { z } from 'zod';
import {
  WorkflowRunSchema,
  MergeQueueResponseSchema,
  CommitSchema,
  type WorkflowRun,
  type MergeQueueEntry,
  type Commit,
} from './types.js';

/**
 * GitHub API client with type-safe wrappers for merge queue monitoring.
 * Combines REST and GraphQL APIs to query workflow runs, queue state, and commits.
 */
export class GitHubClient {
  private readonly octokit: Octokit;
  private readonly graphqlClient: typeof graphql;
  private readonly owner: string;
  private readonly repo: string;

  constructor(token: string, repository: string) {
    this.octokit = new Octokit({ auth: token });
    this.graphqlClient = graphql.defaults({
      headers: { authorization: `token ${token}` },
    });

    const [owner, repo] = repository.split('/');
    this.owner = owner;
    this.repo = repo;
  }

  /**
   * Fetches recent workflow runs created after a specific time.
   * Returns only completed runs, optionally excluding a specific run ID.
   */
  async getWorkflowRuns(
    workflowFileName: string,
    since: Date,
    excludeRunId?: number
  ): Promise<WorkflowRun[]> {
    const response = await this.octokit.actions.listWorkflowRuns({
      owner: this.owner,
      repo: this.repo,
      workflow_id: workflowFileName,
      per_page: 20,
      created: `>=${since.toISOString()}`,
    });

    const runs = z.array(WorkflowRunSchema).parse(response.data.workflow_runs);

    return runs.filter(
      (run) => run.status === 'completed' && run.id !== excludeRunId
    );
  }

  /**
   * Fetches current merge queue entries for a branch via GraphQL.
   * Returns up to 10 PRs waiting in the queue.
   */
  async getMergeQueueEntries(branch: string): Promise<MergeQueueEntry[]> {
    const query = `
      query($owner: String!, $repo: String!, $branch: String!) {
        repository(owner: $owner, name: $repo) {
          mergeQueue(branch: $branch) {
            entries(first: 10) {
              nodes {
                position
                state
                enqueuedAt
                pullRequest {
                  number
                  title
                }
              }
            }
          }
        }
      }
    `;

    const response = await this.graphqlClient<unknown>(query, {
      owner: this.owner,
      repo: this.repo,
      branch,
    });

    const parsed = MergeQueueResponseSchema.parse(response);

    return parsed.repository.mergeQueue?.entries.nodes ?? [];
  }

  /**
   * Fetches recently merged PRs to a branch.
   * Uses PR merge time, not commit timestamps, for accurate merge activity detection.
   */
  async getRecentMerges(branch: string, since: Date): Promise<Array<{ number: number; mergedAt: string; title: string }>> {
    const response = await this.octokit.pulls.list({
      owner: this.owner,
      repo: this.repo,
      state: 'closed',
      base: branch,
      sort: 'updated',
      direction: 'desc',
      per_page: 30,
    });

    return response.data
      .filter((pr) => pr.merged_at !== null)
      .filter((pr) => new Date(pr.merged_at!) >= since)
      .map((pr) => ({
        number: pr.number,
        mergedAt: pr.merged_at!,
        title: pr.title,
      }));
  }

  /**
   * Fetches commits to a branch (used for fallback time-since-merge calculation).
   */
  async getRecentCommits(branch: string, since: Date): Promise<Commit[]> {
    const response = await this.octokit.repos.listCommits({
      owner: this.owner,
      repo: this.repo,
      sha: branch,
      per_page: 30,
    });

    const allCommits = z.array(CommitSchema).parse(response.data);

    return allCommits.filter((commit) => {
      const committerDate = new Date(commit.commit.committer.date);
      return committerDate >= since;
    });
  }

  /**
   * Fetches job details for a specific workflow run.
   * Used to inspect step results from previous monitoring runs.
   */
  async getWorkflowRunJobs(runId: number) {
    const response = await this.octokit.actions.listJobsForWorkflowRun({
      owner: this.owner,
      repo: this.repo,
      run_id: runId,
    });

    return response.data.jobs;
  }

  /**
   * Fetches the default branch name for the repository.
   * Returns the branch name (e.g., 'main', 'devel', 'master').
   */
  async getDefaultBranch(): Promise<string> {
    const response = await this.octokit.repos.get({
      owner: this.owner,
      repo: this.repo,
    });

    return response.data.default_branch;
  }

  /**
   * Builds a URL to the GitHub merge queue page for a branch.
   */
  getQueueUrl(branch: string): string {
    return `https://github.com/${this.owner}/${this.repo}/queue/${branch}`;
  }

  /**
   * Builds a URL to a specific pull request.
   */
  getPrUrl(prNumber: number): string {
    return `https://github.com/${this.owner}/${this.repo}/pull/${prNumber}`;
  }
}
