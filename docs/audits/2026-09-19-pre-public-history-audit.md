# Pre-public history audit — 2026-09-19

Supersedes the 2026-09-18 preliminary audit. Re-run after the rename to
`oldhand`, the packaging restructure, and the merge of the evolution branch.

**Status:** checks complete; owner sign-off still required before the
repository's visibility is changed.

## Scope

All reachable refs in the repository on 2026-09-19: **61 commits**. Every
blob under 2 MB reachable from any ref was decompressed and pattern-scanned,
not just the current tree.

## Results

| Check | Result |
| --- | --- |
| Secret pattern scan over every reachable blob | **No hits** |
| Tracked credential-shaped files (`.env`, `.pem`, `.key`, `.p12`, `.pfx`) | **None** |
| Author / committer identities | One identity, a GitHub noreply address |
| Shipped example records | Rewritten to be unmistakably fictional |

Patterns covered: AWS access key ids (`AKIA`/`ASIA`), GitHub tokens (`ghp_`,
`gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`), GitLab PATs, Slack tokens,
OpenAI and Anthropic API keys, Google API keys, PEM private key headers, JWTs,
and assignment-style secrets (`api_key`, `client_secret`, `password`, `token`)
with a quoted value of 16 or more characters.

### Author metadata

    Mu In Nasif <82433236+IotA-asce@users.noreply.github.com>

The only identity in the history is a GitHub noreply address. No personal or
employer email address is exposed by publishing this history.

### Unreachable objects

`git fsck --no-reflogs --unreachable` reports unreachable trees and blobs in
the local clone. These are ordinary local garbage from rebases, amended
commits and worktree operations. They are not reachable from any ref, so
`git push` does not transmit them and they cannot appear in the published
repository. They are listed here only so the next auditor is not surprised.

## What this audit does not establish

- **`gitleaks` was not run.** The scan above is a pattern review performed
  with `git cat-file` and `grep`, covering the same common credential shapes.
  It is evidence, not proof. Run `gitleaks git --redact --log-opts="--all"`
  in a private environment for an independent second opinion.
- It does not assess whether any example is derived from a real system
  beyond confirming the shipped records are labelled fictional.
- It is not a trademark, license or export review.

Do not paste scanner findings or unredacted history into public issues.

## Required before changing visibility

- [ ] Owner has reviewed this report and accepts the residual risk.
- [ ] Owner confirms the author/committer metadata above may be published.
- [ ] Owner certifies every shipped example is synthetic.
- [ ] GitHub secret scanning and push protection enabled on the repository.
- [ ] Any real credential ever committed has been revoked, independently of
      whether history is rewritten.
