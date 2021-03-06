#!/usr/bin/env bash
# Arguments: Use --pid_file to specify a pid file location.
tox -e py26

function run() {
    .tox/py26/bin/python $@
}
run bin/reddwarf-manage \
    --config-file=etc/reddwarf/reddwarf.conf.test db_wipe \
    reddwarf_test.sqlite mysql fake
run bin/reddwarf-server \
    --fork --config-file=etc/reddwarf/reddwarf.conf.test \
    repo_path=reddwarf_test.sqlite $@

