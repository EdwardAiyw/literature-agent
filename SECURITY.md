# Security policy

Do not post credentials, private research data, or exploitable vulnerability details in a public issue.

To report a vulnerability privately, use GitHub's **Report a vulnerability** option in this repository's Security tab if available. If it is unavailable, contact the repository owner through a private channel and share only the minimum information needed to establish contact. Please avoid public disclosure until the issue can be assessed.

Beta releases are supported on a best effort basis. Install only releases distributed by the repository owner, verify `SHA256SUMS.txt`, and keep API keys and SMTP credentials out of bug reports.

The optional Linux server runtime is single-user and has no application login. Keep its published port bound to loopback and use SSH forwarding. Its persistent secret store is plaintext protected by filesystem permissions; protect the data volume, SSH account and backups. See [server deployment](docs/SERVER_DEPLOYMENT.md).
