# Universal Skills for Claude Code

Comprehensive skill set to enhance assistant capabilities across any project.

---

## 1. Code Review Skill

**Purpose:** Comprehensive code quality and correctness analysis

### When to use:
- After implementing features or fixing bugs
- Before merging to main branch
- When user asks for review

### Review Dimensions:
1. **Correctness**: Edge cases, error handling, type safety, race conditions
2. **Simplification**: Remove duplication, reduce complexity, improve readability
3. **Efficiency**: Algorithm optimization, memory usage, query performance
4. **Test Coverage**: Unit tests, integration tests, edge cases
5. **Security**: Input validation, injection prevention, secrets management
6. **Maintainability**: Single responsibility, clear boundaries, documentation

### Output Format:
```markdown
## Code Review Summary
**Files:** file1.py, file2.js

### Critical Issues (must fix)
- Line 45: Potential null pointer

### High Priority (should fix)
- Line 23: Missing error handling

### Medium Priority (consider)
- Line 12: Better naming possible

### Suggestions (optional)
- Consider extracting common pattern
```

---

## 2. Debug Skill

**Purpose:** Systematic debugging workflow

### Workflow:
1. **Understand Symptom**: Reproduce, isolate, document
2. **Locate Source**: Trace execution, check recent changes, add logging
3. **Identify Root Cause**: Ask "why" iteratively
4. **Implement Fix**: Fix root cause, add tests, verify
5. **Prevent Recurrence**: Add monitoring, update docs

### Common Patterns:
- Null/Undefined errors → Add validation
- Type errors → Check types early
- Off-by-one → Verify loop bounds
- Race conditions → Use locks/synchronization

### Output:
```markdown
## Debug Analysis
**Issue:** Description
**Root Cause:** file:line - Why it happens
**Fix:** Code change
**Verification:** Tests pass ✅
```

---

## 3. Documentation Skill

**Purpose:** Generate clear, comprehensive documentation

### When to use:
- New feature implementation
- API endpoints
- Complex algorithms
- Project architecture overview

### Doc Types:
1. **README**: Project overview, setup, quick start
2. **API Docs**: Endpoints, parameters, examples, responses
3. **Architecture**: System design, component interactions
4. **Code Comments**: Complex logic explanation
5. **Changelog**: Version history, breaking changes

### Best Practices:
- Write for the reader, not the writer
- Include concrete examples
- Keep up to date with code
- Use consistent formatting
- Link related documentation

---

## 4. Testing Skill

**Purpose:** Design and implement comprehensive test suites

### Test Types:
1. **Unit Tests**: Individual functions/methods
2. **Integration Tests**: Component interactions
3. **E2E Tests**: Full user workflows
4. **Property Tests**: Invariants that must hold

### Coverage Goals:
- Core business logic: 90%+
- Error handling paths: 100%
- Utility functions: 80%+
- UI components: 70%+

### Test Quality:
- **Arrange-Act-Assert** pattern
- One assertion per test
- Descriptive test names
- Test both positive and negative cases
- Mock external dependencies

### Output:
```python
def test_function_name():
    """Test description."""
    # Arrange
    input_data = prepare_test_data()

    # Act
    result = function_under_test(input_data)

    # Assert
    assert result.expected_field == expected_value
```

---

## 5. Performance Optimization Skill

**Purpose:** Identify and fix performance bottlenecks

### Analysis Steps:
1. **Profile**: Measure where time/memory is spent
2. **Identify Bottlenecks**: Slow queries, loops, allocations
3. **Optimize**: Apply targeted fixes
4. **Verify**: Measure improvement

### Common Optimizations:
- **Algorithmic**: O(n²) → O(n log n)
- **Caching**: Memoization, LRU cache
- **Database**: Indexes, query optimization, batching
- **Memory**: Reduce allocations, object reuse
- **Parallelism**: Async I/O, thread pools

### Tools:
```bash
# Python profiling
python -m cProfile script.py

# Memory profiling
pip install memory-profiler

# Time measurement
import timeit
timeit.timeit('function()', setup='from module import function', number=1000)
```

---

## 6. Security Review Skill

**Purpose:** Identify security vulnerabilities

### Checklist:
1. **Input Validation**: All user inputs sanitized?
2. **Authentication**: Proper auth checks on protected routes?
3. **Authorization**: Users can't access others' data?
4. **SQL Injection**: Parameterized queries used?
5. **XSS Prevention**: Output encoding applied?
6. **CSRF Protection**: Tokens validated?
7. **Secrets Management**: No hardcoded credentials?
8. **Dependencies**: Known vulnerabilities checked?
9. **Error Handling**: No sensitive info in errors?
10. **Logging**: Security events captured?

### Tools:
```bash
# Dependency check
pip-audit
npm audit

# Static analysis
bandit (Python)
eslint-security (JS)
```

---

## 7. Data Analysis Skill

**Purpose:** Analyze datasets, find patterns, generate insights

### Workflow:
1. **Load Data**: Read from CSV, database, API
2. **Explore**: Basic statistics, distributions, correlations
3. **Visualize**: Charts, histograms, scatter plots
4. **Analyze**: Statistical tests, trend detection
5. **Report**: Key findings with evidence

### Common Operations:
```python
import pandas as pd
import matplotlib.pyplot as plt

# Load
df = pd.read_csv('data.csv')

# Explore
print(df.describe())
print(df.corr())

# Visualize
df.plot(x='date', y='value')
plt.show()

# Analyze
trend = df['value'].rolling(window=7).mean()
```

### Output Format:
```markdown
## Data Analysis Report

**Dataset:** 10,000 records, 15 features
**Period:** Jan 2024 - Jul 2024

### Key Findings
1. **Trend:** 15% growth over period
2. **Correlation:** Strong correlation (0.85) between X and Y
3. **Outliers:** 5 anomalous points detected

### Recommendations
- Investigate outlier causes
- Monitor trend continuation
```

---

## 8. Git & Version Control Skill

**Purpose:** Effective Git usage and collaboration

### Best Practices:
- **Atomic Commits**: One logical change per commit
- **Clear Messages**: What changed and why
- **Feature Branches**: Never commit directly to main
- **Rebase vs Merge**: Clean history preferred
- **Code Review**: PRs before merging

### Commit Message Format:
```
type: short summary

detailed explanation of changes

fixes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Useful Commands:
```bash
# View history
git log --oneline --graph

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Stash changes
git stash push -m "WIP: feature name"

# Cherry-pick specific commit
git cherry-pick <commit-hash>
```

---

## How to Use These Skills

### Invocation Methods:
1. **Explicit**: User says "/code-review" or "use debug skill"
2. **Implicit**: Assistant recognizes task type and applies relevant skill
3. **Combined**: Multiple skills for complex tasks (review + test + docs)

### Adaptation:
- Match project's existing patterns
- Respect team conventions
- Balance thoroughness vs pragmatism
- Explain reasoning, not just conclusions

### Continuous Improvement:
- Learn from feedback
- Update based on lessons learned
- Add new patterns as discovered

---

**Last Updated:** 2026-08-05
**Version:** 1.0
**Total Skills:** 8 universal capabilities
