# Summary

<!-- 1-3 sentences describing what this PR does and why. -->

## Changes

<!-- Bulleted list of the key changes. Reference files/components when useful. -->

-
-
-

## Related Issues

<!-- Link any related issues with "Closes #123", "Fixes #456", or "Refs #789". -->

## Test Plan

<!-- How did you verify this works? Steps a reviewer can follow. -->

- [ ] `npm run lint` passes
- [ ] `npm run build` passes (typecheck + production build)
- [ ] Manually verified in `npm run dev`

## Screenshots / Recordings

<!-- For any UI changes, include before/after screenshots or a short clip. -->

## Checklist

- [ ] No `any` types added without justification
- [ ] New endpoints have an `*-api.ts` raw caller and a `use*` TanStack Query hook
- [ ] New query keys extend `src/lib/query-keys.ts` (not hardcoded)
- [ ] Forms use `react-hook-form` + `zodResolver` with schemas in `src/lib/schemas.ts`
- [ ] No new client state added to Jotai unless it genuinely needs to be global
