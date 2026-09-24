# Real-World Workflow Examples

This directory contains workflow examples that use real public APIs for manual validation and demonstration purposes. These workflows showcase practical use cases combining API calls with data processing using Python and Bash scripts.

## Available Workflows

### 1. **blog-analytics.yaml** - Multi-Step Blog Analytics

Analyzes user activity from JSONPlaceholder API by fetching user profile, posts, and todos, then generating a comprehensive activity report.

**Features:**

- Multiple sequential API calls
- Parallel data analysis (posts and todos)
- Data aggregation and reporting
- Complex data processing with Python

**Usage:**

```bash
# Analyze default user (ID: 1)
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/blog-analytics.yaml

# Analyze specific user
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/blog-analytics.yaml \
  --inputs '{"user_id": 3}'
```

**Expected Output:**

- User profile information
- Post content analysis (total posts, word counts, longest/shortest posts)
- Todo completion rate and productivity metrics
- Overall activity level classification

---

### 2. **github-repo-info.yaml** - GitHub Repository Analysis

Fetches repository information from GitHub API and analyzes popularity, activity, and language usage.

**Features:**

- Multiple GitHub API endpoints
- JSON data processing
- Popularity scoring algorithm
- Multi-language repository analysis

**Usage:**

```bash
# Analyze default repository (anthropics/anthropic-sdk-python)
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/github-repo-info.yaml

# Analyze specific repository
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/github-repo-info.yaml \
  --inputs '{"owner": "temporalio", "repo": "sdk-python"}'

# Analyze your own repository
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/github-repo-info.yaml \
  --inputs '{"owner": "yourusername", "repo": "yourrepo"}'
```

**Expected Output:**

- Repository name, description, and primary language
- Star count, fork count, and open issues
- Popularity score calculation
- Activity level classification
- List of all programming languages used

---

### 3. **ip-geolocation.yaml** - IP Address Geolocation

Looks up IP address geolocation data and generates a location report using the ip-api.com free API.

**Features:**

- IP geolocation lookup
- Bash script for report generation
- Location and network information

**Usage:**

```bash
# Lookup default IP (8.8.8.8 - Google DNS)
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/ip-geolocation.yaml

# Lookup specific IP address
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/ip-geolocation.yaml \
  --inputs '{"ip_address": "1.1.1.1"}'

# Lookup your current public IP (leave empty string)
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/ip-geolocation.yaml \
  --inputs '{"ip_address": ""}'
```

**Expected Output:**

- Country, region, and city
- Latitude and longitude coordinates
- ISP and timezone information
- Formatted location summary

---

### 4. **random-users.yaml** - Random User Profile Generator

Fetches random user profiles from randomuser.me API and generates a user directory with demographics analysis.

**Features:**

- Configurable user count
- User profile processing
- Statistical analysis (average age, gender distribution)
- Array data handling

**Usage:**

```bash
# Generate default (5 users)
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/random-users.yaml

# Generate specific number of users
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/random-users.yaml \
  --inputs '{"count": 10}'

# Maximum allowed: 20 users
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/random-users.yaml \
  --inputs '{"count": 20}'
```

**Expected Output:**

- List of generated user profiles with names, emails, locations
- Total user count
- Average age calculation
- Gender distribution statistics

---

### 5. **country-info.yaml** - Country Information Analysis

Fetches detailed country information from REST Countries API including geography, demographics, and neighboring countries.

**Features:**

- Country data retrieval
- Neighboring countries lookup
- Population density calculation
- Size categorization
- Multi-currency and multi-language support

**Usage:**

```bash
# Get info for default country (US)
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/country-info.yaml

# Get info for specific country (use ISO 3166-1 alpha-2 codes)
uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/country-info.yaml \
  --inputs '{"country_code": "GB"}'  # United Kingdom

uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/country-info.yaml \
  --inputs '{"country_code": "FR"}'  # France

uv run python tools/workflow_cli.py run tests/integration/workflow/examples/real-world/country-info.yaml \
  --inputs '{"country_code": "JP"}'  # Japan
```

**Expected Output:**

- Official country name and capital
- Region and subregion
- Area, population, and population density
- Languages and currencies
- Bordering countries
- Size category classification

---

## Key Features Demonstrated

### 1. **Real API Integration**

All workflows use real, publicly available APIs:

- JSONPlaceholder (blog posts and todos)
- GitHub API (repository information)
- ip-api.com (IP geolocation)
- randomuser.me (user profile generation)
- REST Countries (country data)

### 2. **Data Processing Patterns**

- **Python scripts**: Complex data analysis, JSON parsing, statistical calculations
- **Bash scripts**: Simple report generation, text formatting
- **Output mappings**: Extracting specific fields from API responses using JSONPath

### 3. **Expression Resolution**

- URL template interpolation: `https://api.github.com/repos/${trigger.owner}/${trigger.repo}`
- Query parameter interpolation: `userId: ${trigger.user_id}`
- Activity output chaining: `${fetch_user.output.name}`

### 4. **Input Validation**

- Type constraints (string, integer, array)
- Default values for optional inputs
- Range validation (minimum/maximum)
- Pattern validation (regex for country codes)

### 5. **Complex Workflows**

- Sequential execution (fetch user → fetch posts → analyze)
- Parallel execution (analyze posts and todos simultaneously)
- Multi-step data transformation pipelines

## Common Patterns

### API Call Output Mapping

For API activities, use `$.body.field` to extract response fields:

```yaml
outputs:
  userName: $.body.name
  userEmail: $.body.email
  stars: $.body.stargazers_count
```

### Script Output Mapping

For script activities that output JSON, use `$.output.field`:

```yaml
outputs:
  report: $.output # Entire parsed JSON
  summary: $.output.summary # Specific field
  count: $.output.total_count # Nested field
```

### Chaining Activities

Reference previous activity outputs in subsequent activities:

```yaml
inputs:
  user_name: ${fetch_user.output.userName}
  posts: ${fetch_posts.output.posts}
```

### List/Array Processing

When passing arrays between activities, they're automatically serialized as JSON:

```yaml
# API returns array
outputs:
  posts: $.body # Array of posts

# Python script receives it as JSON string
code: |
  import json
  import os
  posts_json = os.getenv('INPUT_POSTS', '[]')
  posts = json.loads(posts_json)
  # Process the list...
```

## Requirements

- **Temporal dev server** running on `localhost:7233`

  ```bash
  temporal server start-dev
  ```

- **Python 3.12+** with required dependencies

- **Network access** to public APIs (no authentication required for these examples)

## Notes

- These workflows are designed for **manual validation** and **demonstration**, not automated testing
- API rate limits may apply (especially for GitHub API - 60 requests/hour without auth)
- Response times depend on external API availability
- All APIs used are free and do not require authentication
- Some APIs (like ip-api.com) may have usage limits for commercial use

## Troubleshooting

### GitHub API Rate Limiting

If you hit GitHub's rate limit (60 requests/hour), you can:

1. Wait for the rate limit to reset
2. Add a GitHub personal access token (increases limit to 5000/hour)
3. Use a different repository owner/name

### API Timeouts

If workflows timeout:

- Check your internet connection
- Verify the API is accessible from your network
- Increase the timeout value in the workflow definition

### Invalid Output Mappings

Ensure script output mappings use `$.output.field` pattern:

```yaml
# ✅ Correct
outputs:
  result: $.output

# ❌ Incorrect
outputs:
  result: $
```

## Adding New Real-World Examples

When creating new real-world workflow examples:

1. Use free, publicly accessible APIs (no authentication required)
2. Include clear documentation of what the workflow does
3. Provide usage examples with different input parameters
4. Document expected output format
5. Use realistic default values
6. Add input validation where appropriate
7. Follow the output mapping patterns shown above
8. Test manually before committing

## Related Examples

For basic workflow patterns and features, see:

- `../basic/` - Core workflow patterns
- `../api/` - API-specific examples with mock endpoints
- `../loops/` - Loop constructs
- `../conditionals/` - Conditional logic
