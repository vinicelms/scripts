# SSO Credentials

This script is used to list AWS Organization accounts SSO page and set that accounts on `~/.aws/credentials` and `~/.aws/config`

## How to use

### Linux (Linux WSL too)

```shell
git clone https://github.com/vinicelms/scripts.git
cd sso-credentials
python3 -m venv .venv # Optional - remove this option only if you know the impact
source .venv/bin/activate # Optional - remove this option only if you know the impact
pip3 install -r requirements.txt
python3 sso-credentials.py --help
```

### Windows
```shell
git clone https://github.com/vinicelms/scripts.git
cd sso-credentials
python3 -m venv .venv # Optional - remove this option only if you know the impact
.venv/Scripts/activate # Optional - remove this option only if you know the impact
pip3 install -r requirement.txt
python3 sso-credentials.py --help
```