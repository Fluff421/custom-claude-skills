
***

## 7. `mcp-builder/SKILL.md`

```markdown
# MCP Builder Skill

## Purpose
Guide Claude through designing, scaffolding, and implementing Model Context Protocol (MCP) servers that securely connect external APIs, databases, tools, and services — turning one-off integrations into permanent, shareable agent capabilities.

## When to Use This Skill
- You want Claude to connect to an external REST, GraphQL, or gRPC API
- You need Claude to query a database (PostgreSQL, MySQL, SQLite, MongoDB)
- You want to expose a custom tool or function as a persistent Claude capability
- You're building a multi-agent system and need structured tool interfaces
- You want to share an integration with your team via a reusable MCP server

## Instructions for Claude

### Step 1: Gather Requirements
Ask the user:
1. What external system are you connecting to?
2. What operations do you need? (read, write, search, subscribe)
3. What auth method does it use? (API key, OAuth2, JWT, basic auth)
4. Preferred language: TypeScript (recommended) or Python?

### Step 2: Scaffold the Project
