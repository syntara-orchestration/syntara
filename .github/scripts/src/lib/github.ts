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

export class GitHubClient {
  private octokit: Octokit;
  private graphqlClient: typeof graphql;
  private owner: string;
  private repo: string;

  constructor(token: string, repository: string) {
    this.octokit = new Octokit({ auth: token });
    this.graphqlClient = graphql.defaults({
      headers: { authorization: `token ${token}` },
    });

    const [owner, repo] = repository.split('/');
    this.owner = owner;
    this.repo = repo;
  }

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

  async getRecentCommits(branch: string, since: Date): Promise<Commit[]> {
    const response = await this.octokit.repos.listCommits({
      owner: this.owner,
      repo: this.repo,
      sha: branch,
      since: since.toISOString(),
      per_page: 10,
    });

    return z.array(CommitSchema).parse(response.data);
  }

  async getWorkflowRunJobs(runId: number) {
    const response = await this.octokit.actions.listJobsForWorkflowRun({
      owner: this.owner,
      repo: this.repo,
      run_id: runId,
    });

    return response.data.jobs;
  }

  getQueueUrl(branch: string): string {
    return `https://github.com/${this.owner}/${this.repo}/queue/${branch}`;
  }

  getPrUrl(prNumber: number): string {
    return `https://github.com/${this.owner}/${this.repo}/pull/${prNumber}`;
  }
}
