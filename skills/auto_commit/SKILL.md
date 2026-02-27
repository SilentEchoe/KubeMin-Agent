---
description: Automatically commits code changes to the repository after each feature is implemented
always: true
---

# Auto Commit Policy

As an intelligent agent, you MUST obey the following code version control policy:

Whenever you have successfully completed the implementation of a feature, bug fix, or a logical chunk of work requested by the user, you MUST automatically commit the changes using `git`. 

**Do not wait** for the user to explicitly ask "Please commit this code". 

### Workflow Rules:
1. **Verify State:** Ensure the code is tested or at least syntactically valid before committing. Use `git status` to see what has changed.
2. **Atomic Commits:** Only stage and commit the files relevant to the completed feature.
3. **Commit Message:** Write a clear and concise commit message following standard conventional commits format (e.g. `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`).
4. **Push:** After committing, if you have remote access, automatically push the changes with `git push`.
5. **Report:** When notifying the user that the task is finished, explicitly mention that you have successfully committed (and pushed) the code, including the commit hash.
