# GitHub Workflow Guide for FrappeCRM

This guide explains how to properly use Git and GitHub to contribute to the FrappeCRM project.

## Repository Structure

The FrappeCRM project uses a single Git repository structure:

- The main Git repository root is at: `frappe-bench/apps/crm/`
- This is where the `.git` folder is located
- All Git commands should be run from this directory

## Basic Git Workflow

### Step 1: Setting Up

First time setup only:

```bash
# Configure your identity (replace with your actual info)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Step 2: Making Changes

Always start your work from the latest version:

```bash
# Make sure you're in the repository root
cd frappe-bench/apps/crm

# Get the latest changes
git pull origin master
```

### Step 3: Committing Changes

After making your changes:

```bash
# Check what files have been modified
git status

# IMPORTANT: Make sure you're in the repository root (frappe-bench/apps/crm)
# before running add/commit commands

# Stage all changes
git add .

# Alternatively, stage specific files
git add file1.py file2.js

# For deleted files, use git rm
git rm path/to/deleted/file.vue

# Commit your changes with a meaningful message
git commit -m "feat: Add task timer feature"
```

### Step 4: Pushing to GitHub

```bash
# Push your changes to the remote repository
git push origin master  # Or your branch name if not master
```

## Common Issues and Solutions

### File Paths Show `../` Prefix

If `git status` shows file paths with `../` like:

```
modified:  ../frontend/src/components/SomeFile.vue
```

This means you're in a subdirectory below the repository root. Navigate up to the repository root:

```bash
# If you're in frappe-bench/apps/crm/crm
cd ..

# Now you should be in frappe-bench/apps/crm (the repository root)
```

### Best Practices

1. **Always Run Git Commands from the Repository Root**
   - Always cd to `frappe-bench/apps/crm` before running Git commands
   - This ensures all changes in the project are properly tracked

2. **Use Descriptive Commit Messages**
   - Start with a type: `feat:`, `fix:`, `docs:`, `style:`, etc.
   - Keep it concise but clear
   - Examples:
     - `feat: Add AI email generation for bulk leads`
     - `fix: Resolve error in email template rendering`
     - `docs: Update installation instructions`

3. **Pull Before Push**
   - Always run `git pull origin master` before pushing your changes
   - This helps avoid merge conflicts

4. **Check Status Before Committing**
   - Run `git status` to see what files will be included in your commit
   - Make sure you're not accidentally committing unrelated changes

## Branch Workflow (For Larger Features)

For more complex features, consider using feature branches:

```bash
# Create a new branch for your feature
git checkout -b feature-name

# Make your changes, commit them
git add .
git commit -m "feat: Implement new feature"

# Push the branch to GitHub
git push origin feature-name

# When ready, create a Pull Request on GitHub
# After review and approval, the branch will be merged into master
```

## Handling Merge Conflicts

If you encounter merge conflicts:

```bash
# Pull the latest changes
git pull origin master

# Git will indicate files with conflicts
# Open these files and resolve the conflicts manually
# Look for sections marked with <<<<<<< HEAD, =======, and >>>>>>>

# After resolving, stage the files
git add .

# Complete the merge
git commit -m "Resolve merge conflicts"

# Push your changes
git push origin master
```

## Common Git Commands Reference

- `git status`: Check the status of your working directory
- `git add .`: Stage all changes
- `git commit -m "message"`: Commit staged changes
- `git pull`: Get latest changes from remote
- `git push`: Push your changes to remote
- `git log`: View commit history
- `git diff`: View changes between commits
- `git checkout -- file.txt`: Discard changes to a file
- `git reset --hard`: Discard all local changes (use with caution!)

Remember, Git tracks your changes based on where the `.git` directory is located. Always make sure you're in the right directory (`frappe-bench/apps/crm`) when running Git commands. 