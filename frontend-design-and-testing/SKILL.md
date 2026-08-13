
***

## 6. `frontend-design-and-testing/SKILL.md`

```markdown
# Frontend Design + WebApp Testing Skill

## Purpose
Produce high-quality, accessible, production-ready frontend UIs using React + Tailwind/shadcn — then automatically test them end-to-end with Playwright. Eliminates AI-generated "slop" UI by enforcing design system rules and accessibility standards from the start.

## When to Use This Skill
- Building new React components or full page layouts
- Refactoring existing UI to improve quality and accessibility
- Adding Playwright end-to-end tests to a web application
- Generating a complete UI from a wireframe, description, or design spec
- Testing user flows (login, checkout, form submission, navigation)

## Instructions for Claude

### Frontend Design Rules
1. **Always use Tailwind utility classes** — never inline styles unless absolutely necessary
2. **Use shadcn/ui components** as the base (Button, Card, Input, Dialog, Table) — never build from scratch what shadcn provides
3. **Spacing**: use only 4px-base increments (p-1=4px, p-2=8px, p-4=16px, p-8=32px)
4. **Typography**: use `text-sm/base/lg/xl/2xl` — never arbitrary sizes
5. **Accessibility (required on every component)**:
   - All images need `alt` text
   - All interactive elements need `aria-label` or visible label
   - WCAG AA contrast ratio (4.5:1 for text)
   - Keyboard navigation must work (focus rings, tab order)
6. **Responsive by default**: always include `sm:` `md:` `lg:` breakpoints
7. **Dark mode**: include `dark:` variants for all color classes

### Playwright Testing Rules
1. Use `page.getByRole()` and `page.getByLabel()` over CSS selectors
2. Always `await` every interaction
3. Use `expect(page).toHaveURL()` to verify navigation
4. Use `page.screenshot()` for visual regression on key states
5. Group tests with `test.describe()` blocks by feature
6. Always test: render, interaction, error state, and empty state
7. Never use `page.waitForTimeout()` — use `expect().toBeVisible()` waits

## Examples

### React component
```tsx
import { Card, CardHeader, CardContent } from '@/components/ui/card'

export function StatCard({ title, value, trend }: StatCardProps) {
  return (
    <Card className="p-4 dark:bg-gray-900">
      <CardHeader className="text-sm font-medium text-gray-500 dark:text-gray-400">
        {title}
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold">{value}</p>
        <span className={trend > 0 ? 'text-green-500' : 'text-red-500'}>
          {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
        </span>
      </CardContent>
    </Card>
  )
}
