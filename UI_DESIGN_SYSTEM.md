# UI Design System

This is the source of truth for PromptForge visual design, layout, component styling, and
frontend UX conventions. It applies to the bilingual Turkish/English product. Do not invent an
alternate visual system for an individual page.

## Direction

PromptForge is a warm, calm, premium, minimal productivity and knowledge workspace. It is
content-first and approachable to non-technical users, not a generic AI demo. Prefer restraint,
clarity, and generous whitespace. Avoid purple/blue AI gradients, neon, glassmorphism, excessive
shadows, chatbot bubbles, dashboard clutter, raw implementation terminology, and decorative AI
sparkles.

## Color tokens

| Token | Value | Use |
| --- | --- | --- |
| Background | `#F4F0E6` | App background |
| Surface | `#FBF9F3` | Inputs, cards, content panels |
| Sidebar | `#ECE6D8` | Desktop navigation |
| Primary | `#6F7454` | Primary actions, selected controls, links |
| Primary hover | `#5D6246` | Hover/pressed primary controls |
| Dark olive | `#454A35` | Strong olive text/details |
| Text primary | `#272A22` | Primary copy |
| Text secondary | `#747568` | Supporting copy and metadata |
| Border | `#D8D1C1` | Subtle separation |
| Success | `#60785A` | Ready/success states |
| Warning | `#B17A3A` | Preparing/attention states |
| Error | `#B5574D` | Errors/destructive states |

Aim for roughly 70% beige/ivory, 20% neutral text/borders, and 10% khaki/olive accents. Khaki is
for primary actions, selected navigation, focus states, links, checkboxes, and small accents—not
large saturated surfaces.

## Typography

Use Geist; fall back to Inter and system sans-serif. Use restrained semibold weight rather than
large marketing typography.

| Element | Guidance |
| --- | --- |
| Page title | 28–36px, semibold, tight but readable line height |
| Section heading | 20–24px, semibold |
| Body | 15–16px, comfortable line height |
| Metadata | 12–14px, secondary text |
| Labels | 13–14px, medium/semibold, always explicit |

## Application shell and routes

Desktop uses a left navigation and main workspace. Navigation: Create, History, Documents, Ask
Documents. A secondary lower area contains Usage and Settings; the top may hold product identity,
a TR/EN control, and a compact settings/user control. Mobile uses a compact top bar and navigation
drawer. Do not imitate ChatGPT navigation.

| Route | Responsibility |
| --- | --- |
| `/` | Create a prompt and retain generated/executed work in one workflow |
| `/history` | Chronological history and Favorites; details reveal saved work |
| `/documents` | Document library, normal-user readiness, and document actions |
| `/ask` | Grounded document Q&A target experience |
| `/settings` | Preferences and usage where appropriate |

## Create

Use a concise heading, large natural-language input, quick-start presets, response-language
selector, and one primary Generate action. Keep the optimized prompt in the same workflow with
Copy, Favorite, feedback, and Run Prompt. Show execution output with Copy and feedback. Render at
most four clarification questions as a compact form, never chatbot bubbles.

## History

Use a clean chronological list with original-request preview, task type when available, language,
date/time, and favorite state. Support Favorites filtering. Details may show original request,
optimized prompt, execution result, and feedback. Do not show raw PromptSpec JSON by default;
technical detail can become an expandable later feature.

## Documents

Normal-user states are **Preparing**, **Ready**, and **Failed**. Do not present uploaded, parsed,
chunked, embedded, dimensions, or HNSW as primary UX. List filename, type/size, useful language,
readiness, and relevant actions.

## Ask Documents

M5.4 targets a page titled “Ask your documents,” with a short description, ready-document
selector, selected-document chips, large question input, and Ask button. Render a grounded answer
with inline `[1]`, `[2]`, … citations and a Sources section. Source cards show citation ID,
filename, page/range, section, heading, and a short relevant excerpt when available. Inline
citations must focus/highlight their matching source. Source cards below the answer are sufficient
for MVP; a drawer is optional. Insufficient evidence has a clear friendly state. Do not create
chat bubbles or multi-turn chat UI in M5.

## Components

- **Buttons:** primary olive; secondary subtle border; ghost text-only; destructive uses Error.
- **Inputs:** warm Surface, subtle Border, visible olive focus ring, comfortable tap targets.
- **Cards:** Surface, subtle border, 10–14px radius, minimal or no shadow.
- **Badges/status:** compact, muted, always paired with text rather than color alone.
- **Icons:** simple functional line icons, never decorative filler.

## Layout and states

Main content normally stays within 1100–1200px. Use clear vertical rhythm, responsive layouts,
comfortable inputs, limited nesting, and leave empty space empty.

Provide coherent loading, empty, error, success, disabled, selected, preparing, and insufficient
evidence states. Show friendly product language, never machine error codes. Preserve user input and
recoverable state after errors.

## Accessibility and information policy

All controls must be keyboard accessible, semantically labelled, visibly focused, adequately
contrasted, and not color-only. Citation interactions must be accessible by keyboard and expose
their destination.

Use product language: “Preparing document,” not “Generating embeddings”; “Ready,” not “HNSW
indexed.” Implementation details belong only in an optional developer-details view later.

## Milestone boundary

M5.4 applies this direction sufficiently to navigation and the new Ask Documents experience while
preserving current functionality. M7 performs the full design-system migration, product-wide
consistency pass, responsive refinement, accessibility polish, justified animation, and final
demo polish. M5.4 does not need to redesign every existing page.
