#!/bin/bash
set -euo pipefail

BROWSER="${MEDIAUNLOCK_BROWSER:-safari}"

URLS=(
  'https://www.instagram.com/reel/DalkeLOBAmg/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/DbHRk63PlaC/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/DaVOALgzEMc/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/Dbb3EHnvOXg/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/DbYh5wmS21p/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/Da-PFaqJBOZ/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/DZGtSP6x4vc/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/Db8ewR9uoJN/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/DaMbGNOTsQn/?igsi=NTc4MTIwNjQ2YQ=='
  'https://www.instagram.com/reel/DYVbQQ1xC_6/?igsi=NTc4MTIwNjQ2YQ=='
)

printf 'Testing wishlist Instagram reels with browser cookies: %s\n\n' "$BROWSER"

failed=0
for url in "${URLS[@]}"; do
  echo "=== $url ==="
  if MEDIAUNLOCK_BROWSER="$BROWSER" mediaunlock test "$url"; then
    echo "PASS: resolver can inspect this reel"
  else
    echo "FAIL: resolver could not inspect this reel"
    failed=1
  fi
  echo
done

exit "$failed"
