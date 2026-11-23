#!/usr/bin/env bash
# Checks the server's production .env before the stack is started (deploy/README.md, step 5).
#
#   bash deploy/check-env.sh                # checks ./.env
#   bash deploy/check-env.sh path/to/.env
#
# The file is read as text, never run. Only key names are printed, never a value.
# Exit status 0: every check passed. 1: at least one check failed; fix it before `dc up -d`.
set -u

env_file="${1:-.env}"
failures=0
warnings=0

fail() { echo "FAIL  $1"; failures=$((failures + 1)); }
warn() { echo "WARN  $1"; warnings=$((warnings + 1)); }
pass() { echo "ok    $1"; }

if [ ! -f "$env_file" ]; then
  echo "FAIL  $env_file not found: copy deploy/production.env.example to .env first"
  exit 1
fi

KEY_LINE='^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*='

# The value of KEY exactly as written on its line (quotes kept), or nothing if the key is absent.
raw_value() {
  grep -E "^[[:space:]]*$1=" "$env_file" | tail -n 1 | tr -d '\r' | sed -E "s/^[[:space:]]*$1=//"
}

# The value Docker Compose uses: inside the quotes, or up to an inline " # comment", trimmed.
value_of() {
  local v
  v=$(raw_value "$1")
  case "$v" in
    \'*) v=${v#\'}; v=${v%%\'*} ;;
    \"*) v=${v#\"}; v=${v%%\"*} ;;
    *) v=${v%%[[:space:]]#*} ;;
  esac
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  printf '%s' "$v"
}

# --- The file itself --------------------------------------------------------------------------
if [ "$(tr -cd '\r' < "$env_file" | wc -c)" -gt 0 ]; then
  fail "the file has Windows line endings: every value would end in an invisible character (fix: sed -i 's/\r\$//' $env_file)"
else
  pass "Unix line endings"
fi

perm=$(stat -c %a "$env_file" 2>/dev/null || true)
if [ -n "$perm" ] && [ "$perm" != "600" ] && [ "$perm" != "400" ]; then
  warn "permissions are $perm; only you should read it (fix: chmod 600 $env_file)"
fi

if git -C "$(dirname "$env_file")" ls-files --error-unmatch -- "$(basename "$env_file")" >/dev/null 2>&1; then
  fail "the file is tracked by Git: it must never be committed"
fi

placeholders=$(grep -E "$KEY_LINE.*[<>]" "$env_file" | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=.*/\1/' | sort -u | tr '\n' ' ')
if [ -n "$placeholders" ]; then
  fail "placeholder <...> still in: $placeholders"
else
  pass "no <...> placeholders left"
fi

duplicates=$(grep -E "$KEY_LINE" "$env_file" | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=.*/\1/' | sort | uniq -d | tr '\n' ' ')
if [ -n "$duplicates" ]; then
  fail "set more than once (keep one line each): $duplicates"
fi

# --- Required values --------------------------------------------------------------------------
for key in FITSCAN_DOMAIN BASIC_AUTH_USER BASIC_AUTH_HASH POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB AUTO_REMATCH; do
  if [ -z "$(value_of "$key")" ]; then
    fail "$key is missing or empty"
  fi
done

# --- Public address and login -----------------------------------------------------------------
domain=$(value_of FITSCAN_DOMAIN)
domain_re='^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$'
if [ -n "$domain" ]; then
  if [[ $domain =~ $domain_re ]]; then
    pass "FITSCAN_DOMAIN is a host name"
  else
    fail "FITSCAN_DOMAIN must be the host name only, in lower case: no https://, path, port or spaces"
  fi
fi

user=$(value_of BASIC_AUTH_USER)
if [ -n "$user" ]; then
  if [[ $user == *:* || $user =~ [[:space:]] ]]; then
    fail "BASIC_AUTH_USER must not contain a colon or spaces"
  else
    pass "BASIC_AUTH_USER is usable"
  fi
fi

hash_raw=$(raw_value BASIC_AUTH_HASH)
hash=$(value_of BASIC_AUTH_HASH)
bcrypt_re='^\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}$'
if [ -n "$hash" ]; then
  if [[ $hash_raw != \'*\'* ]]; then
    fail "BASIC_AUTH_HASH must be in single quotes: the hash contains \$ signs"
  elif [[ $hash =~ $bcrypt_re ]]; then
    pass "BASIC_AUTH_HASH is a bcrypt hash in single quotes"
  else
    fail "BASIC_AUTH_HASH is not a bcrypt hash: paste the whole output of caddy hash-password"
  fi
fi

# --- PostgreSQL -------------------------------------------------------------------------------
identifier_re='^[A-Za-z_][A-Za-z0-9_]*$'
for key in POSTGRES_USER POSTGRES_DB; do
  value=$(value_of "$key")
  if [ -n "$value" ] && ! [[ $value =~ $identifier_re ]]; then
    fail "$key may contain only letters, digits and underscores"
  fi
done

password=$(value_of POSTGRES_PASSWORD)
if [ -n "$password" ]; then
  if ! [[ $password =~ ^[A-Za-z0-9]+$ ]]; then
    fail "POSTGRES_PASSWORD may contain only letters and digits (it goes into the database URL unencoded); use openssl rand -hex 24"
  elif [ "${#password}" -lt 32 ]; then
    fail "POSTGRES_PASSWORD is shorter than 32 characters; use openssl rand -hex 24"
  elif [ "$password" = "$(value_of POSTGRES_USER)" ]; then
    fail "POSTGRES_PASSWORD must not be the user name"
  else
    pass "POSTGRES_PASSWORD is long and URL-safe"
  fi
fi

# --- Behaviour --------------------------------------------------------------------------------
auto=$(value_of AUTO_REMATCH)
if [ -n "$auto" ]; then
  if [ "$(printf '%s' "$auto" | tr '[:upper:]' '[:lower:]')" = "false" ]; then
    pass "AUTO_REMATCH=false (match runs start by hand)"
  else
    fail "AUTO_REMATCH must be false in production"
  fi
fi

if [ -n "$(value_of CRAWLER_PRIVATE_HOST_ALLOWLIST)" ]; then
  warn "CRAWLER_PRIVATE_HOST_ALLOWLIST is set: only while the demo mock site runs (deploy/README.md, step 8)"
fi
for key in DATABASE_URL REDIS_URL; do
  if grep -qE "^[[:space:]]*$key=" "$env_file"; then
    warn "$key is not needed: docker-compose.yml sets it for the containers"
  fi
done

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures check(s) failed, $warnings warning(s). Fix the FAIL lines, then run this again."
  exit 1
fi
echo "All checks passed ($warnings warning(s))."
