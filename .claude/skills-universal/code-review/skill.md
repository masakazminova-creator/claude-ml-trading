---
name: code-review
description: Comprehensive code review focusing on correctness, efficiency, simplification, and test coverage
---

# Code Review Skill

Perform thorough code review across multiple dimensions.

## When to use
- After implementing a feature or fixing a bug
- Before merging to main branch
- When user asks for review or quality check
- To identify potential issues before they become problems

## Review Dimensions

### 1. Correctness & Bug Prevention
- Edge cases handled? (null values, empty lists, boundary conditions)
- Race conditions in async/concurrent code?
- Proper error handling and resource cleanup?
- Type safety and validation?
- Off-by-one errors in loops/indices?

### 2. Simplification & Readability
- Can this be simplified without losing clarity?
- Duplicate code that should be extracted?
- Over-engineered patterns (unnecessary abstractions)?
- Clear naming conventions?
- Comment density appropriate? (not too much, not too little)

### 3. Efficiency & Performance
- Unnecessary iterations or computations?
- Memory leaks or excessive allocations?
- Database queries optimized (N+1 problem)?
- Algorithm complexity appropriate for scale?
- Caching opportunities?

### 4. Test Coverage
- Unit tests for critical paths?
- Edge cases tested?
- Integration tests for complex flows?
- Mock/stub setup realistic?
- Assertions meaningful?

### 5. Security & Safety
- Input validation and sanitization?
- SQL injection / XSS prevention?
- Secrets management (no hardcoded credentials)?
- Authentication/authorization checks?
- Dependency vulnerabilities?

### 6. Maintainability
- Single responsibility principle?
- Clear module boundaries?
- Documentation up to date?
- Breaking changes documented?
- Version compatibility considered?

## How to perform

1. **Read context first**: Understand surrounding code patterns
2. **Check recent changes**: Git diff or commit history
3. **Run focused analysis**: Pick relevant dimensions based on change type
4. **Provide actionable feedback**: Specific line references with suggestions
5. **Prioritize by severity**: Critical → High → Medium → Low

## Output format

```markdown
## Code Review Summary

**Files reviewed:** file1.py, file2.js
**Change type:** Feature addition / Bug fix / Refactor

### Critical Issues (must fix)
- Line 45: Potential null pointer if `user` is None
- Line 78: SQL injection vulnerability in query construction

### High Priority (should fix)
- Line 23: Missing error handling for network timeout
- Line 90: N+1 query problem - consider batch loading

### Medium Priority (consider improving)
- Line 12: Variable name `x` could be more descriptive
- Line 56: Duplicate logic with lines 34-38

### Suggestions (optional)
- Consider extracting common pattern into utility function
- Add type hints for better IDE support

### Test Coverage
- ✅ Core functionality tested
- ⚠️ Missing edge case for empty input
- ❌ No integration test for error path
```

## Tips

- Match existing code style (don't impose personal preferences)
- Explain WHY something is an issue, not just WHAT
- Provide concrete examples of better approaches
- Balance perfection vs pragmatism
- Focus on code, not coder
