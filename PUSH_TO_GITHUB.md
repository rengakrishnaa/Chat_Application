# Push this project to GitHub

## Step 1: Create a new repository on GitHub

1. Open **https://github.com/new**
2. Sign in if needed.
3. Set **Repository name** (e.g. `VeriTree-Chat-Application` or `Chat_Application`).
4. Choose **Public**.
5. Do **not** add a README, .gitignore, or license (this project already has them).
6. Click **Create repository**.

## Step 2: Add the remote and push

In a terminal, from this project folder, run (replace with your actual GitHub username and repo name):

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

Example if your username is `johndoe` and repo name is `VeriTree-Chat-Application`:

```bash
git remote add origin https://github.com/johndoe/VeriTree-Chat-Application.git
git push -u origin main
```

If you already added a remote and need to change the URL:

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

## Step 3: Verify

Refresh the repo page on GitHub; you should see all project files and the README.
