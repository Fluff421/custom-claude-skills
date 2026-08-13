# Skill Seekers

## Purpose
Automatically convert any documentation website, GitHub repository, or PDF into a fully packaged, production-ready Claude Agent Skill (SKILL.md + directory structure), complete with conflict detection and optimized prompts.

## When to Use This Skill
- You want Claude to become an expert on any library, framework, API, or internal docs
- You need to turn raw documentation into a reusable, installable skill without writing it manually
- You want to onboard Claude to a new codebase or tool quickly

## How It Works
1. Accept a documentation URL, GitHub repo URL, or PDF as input
2. Scrape and parse all structured content (headings, code blocks, API signatures, examples)
3. Identify key concepts, patterns, functions, and usage examples
4. Engineer optimized prompts from the extracted content
5. Detect conflicts with existing skills
6. Output a complete, installable SKILL.md file with metadata, instructions, and examples

## Instructions for Claude
When activated, do the following:
1. Ask the user for: (a) a documentation URL, GitHub repo URL, or PDF, and (b) the desired skill name
2. Fetch and parse all content from the source
3. Extract: core concepts, key functions/APIs, usage patterns, common errors, and best practices
4. Structure the output as a complete SKILL.md with sections: Purpose, When to Use, Instructions, Examples, and Edge Cases
5. Flag any conflicts with known existing skills
6. Output the complete SKILL.md content ready to save

## Examples
- Input: https://docs.stripe.com → Output: stripe-payments/SKILL.md with full Stripe API expertise
- Input: https://github.com/pallets/flask → Output: flask-web/SKILL.md with Flask routing, blueprints, and patterns
- Input: internal-api-docs.pdf → Output: internal-api/SKILL.md with all endpoint patterns

## Edge Cases
- If the source is behind a login wall, ask the user to paste the raw content instead
- If the docs are very large (>500 pages), ask the user which sections to prioritize
- If conflicts are detected with existing skills, list them and ask whether to merge or keep separate

## Tips
- Always include at least 3 concrete usage examples in the generated skill
- Prefer extracting actual code snippets over prose descriptions
- Keep generated SKILL.md files under 2000 lines for performance
