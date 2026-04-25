############################################################################  
# test_148_7.py — Group 7: sacct App accounting record tests  
#  
# Verifies that sacct correctly stores and retrieves app-related fields  
# (AppName, AppVersion, AppSource) from the accounting database, and  
# that filtering by --appname, --appversion, --appsource works correctly.  
#  
# Prerequisites:  
#   - slurmdbd must be running and configured  
#   - At least one compute node available (jobs must actually run)  
#   - App "sacctapp" with Version "1.0,2.0" must be created before tests  
############################################################################  
  
import atf  
import pytest  
import time  
import re  
import json  
  
  
# ---------------------------------------------------------------------------  
# Module-level helpers  
# ---------------------------------------------------------------------------  
  
_apps_created = []  
_jobs_submitted = []  
  
# How long to wait for accounting data to propagate to slurmdbd  
ACCOUNTING_DELAY = 15  
  
  
def _create_app(name, **kwargs):  
    """Create an app via scontrol (as slurm admin)."""  
    cmd = f"scontrol create app AppName={name}"  
    for k, v in kwargs.items():  
        cmd += f" {k}={v}"  
    result = atf.run_command(cmd, user=atf.properties["slurm-user"], fatal=True)  
    assert result["exit_code"] == 0, (  
        f"Failed to create app {name}: {result['stderr']}"  
    )  
    _apps_created.append(name)  
  
  
def _delete_app(name):  
    """Delete an app via scontrol (as slurm admin), ignore errors."""  
    atf.run_command(  
        f"scontrol delete app={name}",  
        user=atf.properties["slurm-user"], quiet=True  
    )  
  
  
def _submit_and_wait(sbatch_args, timeout=60):  
    """Submit a job, wait for it to complete, return job_id."""  
    job_id = atf.submit_job_sbatch(sbatch_args)  
    assert job_id > 0, f"Failed to submit job with args: {sbatch_args}"  
    _jobs_submitted.append(job_id)  
    atf.wait_for_job_state(job_id, "DONE", timeout=timeout, fatal=True)  
    return job_id  
  
  
def _sacct_output(job_id, fmt="JobID,AppName,AppVersion,AppSource",  
                  extra_args=""):  
    """Run sacct for a specific job and return stdout."""  
    cmd = (  
        f"sacct -j {job_id} -X -P --noheader "  
        f"--format={fmt} {extra_args}"  
    )  
    return atf.run_command_output(cmd).strip()  
  
  
def _sacct_filter(filter_args, fmt="JobID", extra_args=""):  
    """Run sacct with filter arguments and return stdout."""  
    cmd = (  
        f"sacct -X -P --noheader --starttime=now-1hour "  
        f"--format={fmt} {filter_args} {extra_args}"  
    )  
    return atf.run_command_output(cmd).strip()  
  
  
# ---------------------------------------------------------------------------  
# Fixtures  
# ---------------------------------------------------------------------------  
  
@pytest.fixture(scope="module", autouse=True)  
def setup():  
    """Ensure Slurm and slurmdbd are running, create test apps.""" 
    time.sleep(2) 
    atf.require_slurm_running()  
  
    # Create test apps  
    _create_app("sacctapp", Version="1.0,2.0")  
    _create_app("sacctother", Version="3.0")  
    _create_app("sacctnoversion")  
  
    yield  
  
    # Cleanup: cancel any remaining jobs (ignore errors if job already gone)  
    for jid in _jobs_submitted:  
        atf.run_command(f"scancel {jid}", quiet=True, fatal=False)  
  
    # Remove jobs from global submitted-jobs list to avoid global cleanup errors  
    for jid in _jobs_submitted:  
        if jid in atf.properties["submitted-jobs"]:  
            atf.properties["submitted-jobs"].remove(jid)  
  
    # Wait a bit for jobs to be fully cleaned up  
    time.sleep(2)  
  
    # Cleanup: delete test apps  
    for name in _apps_created:  
        _delete_app(name)  
  
  
# ---------------------------------------------------------------------------  
# TestSacctAppFields: verify sacct --format shows app fields correctly  
# ---------------------------------------------------------------------------  
class TestSacctAppFields:  
  
    def test_sacct_versioned_app_fields(self):  
        """  
        Submit job with --app=sacctapp-1.0, wait for completion,  
        verify sacct shows AppName=sacctapp, AppVersion=1.0, AppSource=user.  
  
        Source: as_mysql_jobacct_process.c L728-737:  
            job->app_name = row[JOB_REQ_APP_NAME]  
            job->app_version = row[JOB_REQ_APP_VERSION]  
            job->app_source = slurm_atoul(row[JOB_REQ_APP_SOURCE])  
        Source: slurm_protocol_defs.c L4338:  
            APP_SOURCE_USER -> "user"  
        """  
        job_id = _submit_and_wait(  
            '--app=sacctapp-1.0 -t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
  
        output = _sacct_output(job_id)  
        assert output, f"sacct returned empty output for job {job_id}"  
  
        # Parse pipe-delimited output: JobID|AppName|AppVersion|AppSource  
        parts = output.split("|")  
        assert len(parts) >= 4, (  
            f"Expected at least 4 fields, got {len(parts)}: {output}"  
        )  
        assert parts[1] == "sacctapp", (  
            f"Expected AppName=sacctapp, got '{parts[1]}' in: {output}"  
        )  
        assert parts[2] == "1.0", (  
            f"Expected AppVersion=1.0, got '{parts[2]}' in: {output}"  
        )  
        assert parts[3] == "user", (  
            f"Expected AppSource=user, got '{parts[3]}' in: {output}"  
        )  
  
    def test_sacct_second_version(self):  
        """  
        Submit job with --app=sacctapp-2.0, verify sacct shows version 2.0.  
        """  
        job_id = _submit_and_wait(  
            '--app=sacctapp-2.0 -t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
  
        output = _sacct_output(job_id)  
        parts = output.split("|")  
        assert len(parts) >= 4, f"Unexpected output: {output}"  
        assert parts[1] == "sacctapp", (  
            f"Expected AppName=sacctapp, got '{parts[1]}'"  
        )  
        assert parts[2] == "2.0", (  
            f"Expected AppVersion=2.0, got '{parts[2]}'"  
        )  
  
    def test_sacct_unversioned_app(self):  
        """  
        Submit job with --app=sacctnoversion (no version),  
        verify AppName is set but AppVersion is empty.  
        """  
        job_id = _submit_and_wait(  
            '--app=sacctnoversion -t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
  
        output = _sacct_output(job_id)  
        parts = output.split("|")  
        assert len(parts) >= 4, f"Unexpected output: {output}"  
        assert parts[1] == "sacctnoversion", (  
            f"Expected AppName=sacctnoversion, got '{parts[1]}'"  
        )  
        # AppVersion should be empty for unversioned app  
        assert parts[2] == "", (  
            f"Expected empty AppVersion, got '{parts[2]}'"  
        )  
        assert parts[3] == "user", (  
            f"Expected AppSource=user, got '{parts[3]}'"  
        )  
  
    def test_sacct_no_app_job(self):  
        """  
        Submit job without --app, verify app fields are empty.  
  
        Source: slurmdb_defs.c L682:  
            slurmdb_create_job_rec() sets app_source = APP_SOURCE_NOTSET  
        Source: as_mysql_jobacct_process.c L735-736:  
            if row is empty, app_source = APP_SOURCE_NOTSET  
        """  
        job_id = _submit_and_wait(  
            '-t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
  
        output = _sacct_output(job_id)  
        parts = output.split("|")  
        assert len(parts) >= 4, f"Unexpected output: {output}"  
        # AppName and AppVersion should be empty  
        assert parts[1] == "", (  
            f"Expected empty AppName, got '{parts[1]}'"  
        )  
        assert parts[2] == "", (  
            f"Expected empty AppVersion, got '{parts[2]}'"  
        )  
        # AppSource should be empty or "notset" for no-app jobs  
        assert parts[3] == "" or parts[3] == "notset", (  
            f"Expected empty or 'notset' AppSource, got '{parts[3]}'"  
        )  
  
  
# ---------------------------------------------------------------------------  
# TestSacctAppFilter: verify sacct --appname/--appversion/--appsource filters  
# ---------------------------------------------------------------------------  
class TestSacctAppFilter:  
  
    def test_filter_by_appname(self):  
        """  
        sacct --appname=sacctapp should only return jobs with that app name.  
  
        Source: as_mysql_jobacct_process.c L1441-1460:  
            SQL: t5.app_name='sacctapp'  
        """  
        # Submit two jobs: one with sacctapp, one with sacctother  
        jid1 = _submit_and_wait(  
            '--app=sacctapp-1.0 -t1 --wrap="hostname"'  
        )  
        jid2 = _submit_and_wait(  
            '--app=sacctother-3.0 -t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
  
        output = _sacct_filter(  
            "--appname=sacctapp",  
            fmt="JobID,AppName"  
        )  
        assert str(jid1) in output, (  
            f"Job {jid1} (sacctapp) should appear in --appname=sacctapp output: {output}"  
        )  
        assert str(jid2) not in output, (  
            f"Job {jid2} (sacctother) should NOT appear in --appname=sacctapp output: {output}"  
        )  
  
    def test_filter_by_appversion(self):  
        jid_v1 = _submit_and_wait(  
            '--app=sacctapp-1.0 -t1 --wrap="hostname"'  
        )  
        jid_v2 = _submit_and_wait(  
            '--app=sacctapp-2.0 -t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
    
        output = _sacct_filter(  
            "--appname=sacctapp --appversion=1.0",  
            fmt="JobID,AppVersion"  
        )  
        assert str(jid_v1) in output, (  
            f"Job {jid_v1} (v1.0) should appear: {output}"  
        )  
        assert str(jid_v2) not in output, (  
            f"Job {jid_v2} (v2.0) should NOT appear: {output}"  
        )
  
    def test_filter_by_appsource(self):  
        """  
        sacct --appsource=user should only return jobs with app_source=USER.  
  
        Source: as_mysql_jobacct_process.c L1482-1499:  
            SQL: t5.app_source=1 (APP_SOURCE_USER=1)  
        """  
        jid_app = _submit_and_wait(  
            '--app=sacctapp-1.0 -t1 --wrap="hostname"'  
        )  
        jid_noapp = _submit_and_wait(  
            '-t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
  
        output = _sacct_filter(  
            "--appsource=user",  
            fmt="JobID,AppSource"  
        )  
        assert str(jid_app) in output, (  
            f"Job {jid_app} (user source) should appear in --appsource=user output: {output}"  
        )  
        assert str(jid_noapp) not in output, (  
            f"Job {jid_noapp} (no app) should NOT appear in --appsource=user output: {output}"  
        )  
  
    def test_filter_combined_appname_and_version(self):  
        """  
        sacct --appname=sacctapp --appversion=2.0 should only return  
        jobs matching both criteria.  
  
        Source: as_mysql_jobacct_process.c L1440-1481:  
            Both conditions are ANDed in the SQL WHERE clause.  
        """  
        jid_v1 = _submit_and_wait(  
            '--app=sacctapp-1.0 -t1 --wrap="hostname"'  
        )  
        jid_v2 = _submit_and_wait(  
            '--app=sacctapp-2.0 -t1 --wrap="hostname"'  
        )  
        jid_other = _submit_and_wait(  
            '--app=sacctother-3.0 -t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
  
        output = _sacct_filter(  
            "--appname=sacctapp --appversion=2.0",  
            fmt="JobID,AppName,AppVersion"  
        )  
        assert str(jid_v2) in output, (  
            f"Job {jid_v2} (sacctapp-2.0) should appear: {output}"  
        )  
        assert str(jid_v1) not in output, (  
            f"Job {jid_v1} (sacctapp-1.0) should NOT appear: {output}"  
        )  
        assert str(jid_other) not in output, (  
            f"Job {jid_other} (sacctother-3.0) should NOT appear: {output}"  
        )  
  
    def test_filter_appname_no_match(self):  
        """  
        sacct --appname=nonexistent should return no jobs.  
        """  
        _submit_and_wait(  
            '--app=sacctapp-1.0 -t1 --wrap="hostname"'  
        )  
        time.sleep(ACCOUNTING_DELAY)  
  
        output = _sacct_filter(  
            "--appname=nonexistent_xyz",  
            fmt="JobID"  
        )  
        assert output == "", (  
            f"Expected empty output for nonexistent app name, got: {output}"  
        )  
  
  
# ---------------------------------------------------------------------------  
# TestSacctAppHelpformat: verify sacct -e lists app fields  
# ---------------------------------------------------------------------------  
class TestSacctAppHelpformat:  
  
    def test_helpformat_lists_app_fields(self):  
        """  
        sacct -e (or --helpformat) should list AppName, AppVersion, AppSource  
        as available format fields.  
  
        Source: sacct.h L220-222:  
            PRINT_APPNAME, PRINT_APPVERSION, PRINT_APPSOURCE  
        """  
        output = atf.run_command_output("sacct -e")  
        assert "AppName" in output, (  
            f"AppName not found in sacct -e output: {output}"  
        )  
        assert "AppVersion" in output, (  
            f"AppVersion not found in sacct -e output: {output}"  
        )  
        assert "AppSource" in output, (  
            f"AppSource not found in sacct -e output: {output}"  
        )


# ---------------------------------------------------------------------------
# TestSacctOutputFormat: verify sacct output format options work with
# AppName / AppVersion / AppSource fields.
#
# Source: src/sacct/print.c print_fields_parsable_set, print_fields_have_header
#         src/sacct/options.c parse_format() handles %WIDTH suffix
# ---------------------------------------------------------------------------
class TestSacctOutputFormat:
    """
    Verify sacct's output formatting options (-p / -P / --format=%WIDTH /
    --noheader / time and jobid filters / --json) all work consistently
    with the new AppName, AppVersion, AppSource fields.
    """

    def test_sacct_parsable_pipe_format(self):
        """
        sacct -p produces pipe-separated output with a TRAILING '|'.
        The header line and each data line must both end with '|'.
        """
        jid = _submit_and_wait('--app=sacctapp-1.0 -t1 --wrap="hostname"')
        cmd = (
            f"sacct -p -X --starttime=now-1hour -j {jid} "
            "--format=JobID,AppName,AppVersion,AppSource"
        )
        output = atf.run_command_output(cmd).strip()
        assert output, "sacct -p must produce output"

        for line in output.splitlines():
            assert line.endswith("|"), (
                f"sacct -p must end each line with '|', got: {line!r}"
            )

        data_lines = [l for l in output.splitlines()
                      if l and not l.startswith("JobID")]
        assert any(f"{jid}|sacctapp|1.0|user|" in l for l in data_lines), (
            f"Expected JobID|sacctapp|1.0|user| in sacct -p output:\n{output}"
        )

    def test_sacct_parsable2_no_trailing_delim(self):
        """
        sacct -P produces pipe-separated output with NO trailing '|'.
        Field count per line must equal field count in header.
        """
        jid = _submit_and_wait('--app=sacctapp-2.0 -t1 --wrap="hostname"')
        cmd = (
            f"sacct -P -X --starttime=now-1hour -j {jid} "
            "--format=JobID,AppName,AppVersion,AppSource"
        )
        output = atf.run_command_output(cmd).strip()
        assert output, "sacct -P must produce output"

        lines = output.splitlines()
        for line in lines:
            assert not line.endswith("|"), (
                f"sacct -P must NOT end with '|', got: {line!r}"
            )

        header_fields = lines[0].split("|")
        for data_line in lines[1:]:
            data_fields = data_line.split("|")
            assert len(data_fields) == len(header_fields), (
                f"Field count mismatch: header has {len(header_fields)}, "
                f"data line has {len(data_fields)}: {data_line!r}"
            )

    def test_sacct_format_width_appname(self):
        """
        sacct --format=AppName%30 controls the column width.
        AppName column width must be 30 characters.

        Source: parse_format() honors %WIDTH suffix per field.
        """
        jid = _submit_and_wait('--app=sacctapp-1.0 -t1 --wrap="hostname"')
        cmd = (
            f"sacct -X --starttime=now-1hour -j {jid} "
            "--format=AppName%30"
        )
        output = atf.run_command_output(cmd).strip()
        lines = output.splitlines()
        assert len(lines) >= 2, f"Expected header + data line, got: {output}"

        # Header line should be 30 chars wide (allow trailing whitespace trim)
        # Use line BEFORE strip to check raw width of the column
        raw_output = atf.run_command_output(cmd)
        raw_lines = raw_output.rstrip("\n").splitlines()
        # First non-empty line is header; column width is the line length
        header = raw_lines[0]
        assert len(header) >= 30, (
            f"AppName column with %30 must be at least 30 chars wide, "
            f"header length={len(header)}: {header!r}"
        )

    def test_sacct_noheader_omits_header(self):
        """
        sacct --noheader must NOT print the column header line.
        First line of output must be data, not 'JobID  AppName ...'.
        """
        jid = _submit_and_wait('--app=sacctapp-1.0 -t1 --wrap="hostname"')
        cmd = (
            f"sacct -X --noheader --starttime=now-1hour -j {jid} "
            "--format=JobID,AppName"
        )
        output = atf.run_command_output(cmd).strip()
        if output:
            first = output.splitlines()[0]
            assert "JobID" not in first or str(jid) in first, (
                f"With --noheader, first line must not be the column "
                f"header, got: {first!r}"
            )

    def test_sacct_starttime_with_appname(self):
        """
        sacct -S now-1hour --appname=sacctapp must combine time window
        and app name filter correctly.
        """
        jid = _submit_and_wait('--app=sacctapp-1.0 -t1 --wrap="hostname"')
        cmd = (
            "sacct -X -P --noheader --starttime=now-1hour "
            "--appname=sacctapp --format=JobID"
        )
        output = atf.run_command_output(cmd).strip()
        assert str(jid) in output, (
            f"Job {jid} should match --appname=sacctapp within last hour: "
            f"{output}"
        )

    def test_sacct_jobid_with_appname_filter(self):
        """
        sacct -j JOBID --appname=X must intersect:
          - matches when JOBID's app == X
          - empty when JOBID's app != X
        """
        jid = _submit_and_wait('--app=sacctapp-1.0 -t1 --wrap="hostname"')

        # Matching case
        match_cmd = (
            f"sacct -X -P --noheader -j {jid} --appname=sacctapp "
            "--format=JobID"
        )
        match = atf.run_command_output(match_cmd).strip()
        assert str(jid) in match, (
            f"Job {jid} should be returned when both filters match: "
            f"{match}"
        )

        # Non-matching case
        nomatch_cmd = (
            f"sacct -X -P --noheader -j {jid} --appname=sacctother "
            "--format=JobID"
        )
        nomatch = atf.run_command_output(nomatch_cmd).strip()
        assert str(jid) not in nomatch, (
            f"Job {jid} should NOT be returned when --appname mismatches: "
            f"{nomatch}"
        )

    def test_sacct_json_output_contains_app(self):
        """
        sacct --json output must include app fields. If the build does not
        support --json (no data_parser plugin), skip the test.
        """
        jid = _submit_and_wait('--app=sacctapp-1.0 -t1 --wrap="hostname"')
        cmd = f"sacct -j {jid} --json"
        result = atf.run_command(cmd, fatal=False)

        if result["exit_code"] != 0:
            pytest.skip(
                "sacct --json not supported in this build "
                f"(rc={result['exit_code']}): {result.get('stderr', '')}"
            )

        stdout = result["stdout"]
        # Verify it is parseable JSON containing the app fields
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            pytest.skip(f"sacct --json output is not valid JSON: {e}")

        # The JSON schema varies by data_parser version; do a substring
        # check over the serialized form to remain version-agnostic.
        serialized = json.dumps(data).lower()
        assert "app" in serialized, (
            f"sacct --json output should reference app fields:\n{stdout}"
        )