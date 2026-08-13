# Policy for AI-Assisted Contributions

This policy uses the term "AI" as shorthand for technology that is generally built using the machine learning approach. In this sense the term "AI" can refer to any assistive tools, including those considered as autonomous and semi-autonomous, such as large language models (LLMs), text or image generators, and agentic systems that are available as a service or trained locally.

This policy applies to the following projects and resources:

1. All public repositories under the [Syntara Orchestration](https://github.com/syntara-orchestration) project on GitHub.
2. Public communication platforms and channels associated with the project, such as official discussion forums, Matrix channels, and GitHub discussions.

> **Note:** The above projects and resources **MAY have their own AI policies** which MAY expand or be more restrictive than this policy.

## Principles

1. Contributors MAY use the assistance of AI tools for contributing [^1] to the above projects and resources, provided that they take full responsibility for their contributions and follow the principles described in this policy.

2. All contributions assisted by AI tools MUST adhere to any specific project or platform standards, conventions and contributing guidelines, including code of conduct and license compliance. This document seeks to clarify tool-specific considerations but in no way replaces the governing documents and good contributing practices.

3. Contributors are fully accountable for the contributions they make with or without AI assistance. This also applies to persons who authorize actions initiated by AI tools.

4. Any autonomous contributions submitted by AI tools MAY be rejected by resource maintainers without prior justification.

   a. Autonomous actions performed by AI tools used by resource maintainers for validation and automation purposes (for example, automatic releasing, testing, spam filtering, and AI contribution detection) SHOULD be reviewed and manually authorized by the maintainers.

5. The use of AI tools MUST be explicitly disclosed by the author when a significant part of the contribution is taken from the AI tools output without significant changes. Grammar, spelling, and stylistic corrections do not need disclosure.

   a. For code contributions, the contributor MAY use a short commit message trailer.
   b. For other contributions, disclosure MAY include a short preamble.
   c. We recommend using the following statement as a disclosure: `Assisted-by:` followed by any information about the contributor’s use of AI tools that they consider relevant, for example:

      i. `Assisted-by: gpt-5.4`
      ii. `Assisted-by: Opus 4.6`
      iii. `Assisted-by: locally trained model`

The key words "MAY", "MUST", "MUST NOT", and "SHOULD" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

This AI policy was adapted from AI policies of other open source projects, including:

* The Ansible Project
* The Fedora Project
* The Linux Foundation

## Reporting policy violations

Policy violations should be reported via [codeofconduct@syntara-orchestration.org](mailto:codeofconduct@syntara-orchestration.org).

[^1]: For the purposes of this document, contributions include, but are not limited to, opening issues, creating pull requests with code or documentation changes, participating in discussions, making comments, creating posts in the forum, and other related activities.
