<?php

$challenge = getenv('LETS_ENCRYPT_CHALLENGE');
if (!empty($challenge)) {
    echo $challenge;
    exit();
}

echo "not cool.";
