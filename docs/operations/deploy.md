# Deploy checklist

Use this checklist before deploying or tagging Fanpage Agent.

## 1. Check the working tree

```bash
git status --short
```

Review unrelated local changes before creating release notes.

## 2. Run tests

```bash
python3 -m unittest discover -s tests -v
```

## 3. Generate release notes

Preview the changelog for the next version:

```bash
./scripts/changelog.sh v0.2.0
```

Write the release section into `CHANGELOG.md`:

```bash
./scripts/changelog.sh v0.2.0 --write
```

If you only want the latest tag range:

```bash
./scripts/changelog.sh v0.2.0 --latest --write
```

If you need an explicit range:

```bash
./scripts/changelog.sh v0.2.0 --range v0.1.0..HEAD --write
```

## 4. Commit release notes

```bash
git add cliff.toml CHANGELOG.md scripts/changelog.sh docs/operations/deploy.md README.md
git commit -m "docs: add release notes workflow"
```

## 5. Tag the release

```bash
git tag v0.2.0
git push origin main --tags
```

## 6. Deploy

Run the project-specific deployment command after the changelog commit and tag are ready.
