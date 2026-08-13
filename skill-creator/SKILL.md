
***

## 4. `skill-creator/SKILL.md`

```markdown
# Skill Creator

## Purpose
Draft, test, iterate, and package new Claude Agent Skills (SKILL.md files + directory structure) from a plain-language description of a workflow, task, or SOP. Turn any repeatable process into an installable, shareable skill in one session.

## When to Use This Skill
- You have a repeatable workflow you want Claude to execute consistently every time
- You want to encode a Standard Operating Procedure (SOP) as a reusable skill
- You need to build a new skill but don't know how to structure SKILL.md files
- You want to package and share a workflow with your team

## How It Works
1. Accept a plain-language description of the desired skill behavior
2. Ask clarifying questions to define: trigger conditions, step-by-step instructions, expected inputs/outputs, and edge cases
3. Draft a complete SKILL.md with all required sections
4. Self-test by simulating the skill against 2-3 example inputs
5. Fix any gaps or ambiguities identified during testing
6. Output the final, installable skill package

## Instructions for Claude
When activated:
1. Ask: "Describe the task or workflow you want this skill to perform. What are the inputs, the steps, and the expected output?"
2. Draft a SKILL.md with these required sections:
   - **Purpose** — one sentence describing what the skill does
   - **When to Use** — bullet list of trigger conditions
   - **How It Works** — numbered steps of the process
   - **Instructions for Claude** — detailed directives Claude must follow
   - **Examples** — at least 3 concrete input/output pairs
   - **Edge Cases** — at least 3 failure modes and how to handle them
3. Simulate the skill on 2 test inputs and verify the output matches expectations
4. Revise any sections that produce incorrect or vague outputs
5. Present the final SKILL.md, ready to save

## Examples
- Input: "Summarize any YouTube video into 5 bullet points" → Output: youtube-summarizer/SKILL.md
- Input: "Turn messy meeting notes into a clean action item list" → Output: meeting-notes/SKILL.md
- Input: "Review any Python function for security vulnerabilities" → Output: security-review/SKILL.md

## Edge Cases
- If the workflow is too vague, ask for a concrete example before drafting
- If the skill overlaps with an existing one, flag it and offer to extend vs. create new
- If the skill requires external tools or APIs, note dependencies in the SKILL.md header
- If self-testing reveals contradictions, resolve them before final output

## Quality Checklist (run before outputting)
- [ ] Purpose is one clear sentence
- [ ] At least 3 When to Use bullets
- [ ] Instructions are numbered and unambiguous
- [ ] At least 3 examples with real inputs and outputs
- [ ] At least 3 edge cases covered
- [ ] Skill is under 2000 lines
