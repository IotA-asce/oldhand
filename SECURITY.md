# Security Policy

## Supported versions

Security fixes are made for the latest released version and the current default
branch when feasible. Versions that are no longer maintained may require an
upgrade before a fix can be applied.

## Reporting a vulnerability

Please do not report suspected vulnerabilities in public issues, discussions,
or pull requests.

Use the repository's private security-advisory reporting flow if it is enabled.
If that flow is unavailable, contact the project maintainer at **[SECURITY
CONTACT TO BE ADDED BEFORE PUBLIC LAUNCH]** with:

- a concise description of the issue and affected versions;
- reproduction steps or a proof of concept that avoids exposing real data;
- potential impact; and
- any suggested mitigation.

Please allow a reasonable time for acknowledgement and investigation before
public disclosure. The project will aim to acknowledge valid reports promptly,
keep reporters informed about material progress, coordinate a fix and release
when appropriate, and credit reporters only with their permission.

## Scope

Lore is designed to operate on local files. Security reports are especially
useful for issues involving unsafe file writes, path traversal, archive
corruption, secret exposure, command execution, dependency compromise, or
privacy regressions. Reports about deployment environments or integrations are
also welcome when the behavior is attributable to this project.

Do not access, alter, or exfiltrate data that you do not own or have explicit
permission to test.
