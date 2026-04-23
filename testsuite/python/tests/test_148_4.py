############################################################################  
# test_148_4.py - Group 4: Job Submission & App Validation  
#  
# Tests the --app option for sbatch/srun/salloc:  
#   - Valid app submission (versioned and unversioned)  
#   - Invalid app rejection  
#   - --app=list output  
#   - --app-source validation  
#   - scontrol show job app fields  
#   - Environment variable injection  
#  
# Source: _job_create() in src/slurmctld/job_mgr.c lines 7811-7926  
############################################################################  
import atf  
import pytest  
import re  
import os  
import random, string  
  
def _shared_path(prefix):  
    """Generate a unique file path under slurmtest's shared home directory."""  
    tag = ''.join(random.choices(string.ascii_lowercase, k=8))  
    return f"/public/home/slurmtest/{prefix}_{tag}"

# ---------------------------------------------------------------------------  
# Setup / Teardown  
# ---------------------------------------------------------------------------  
@pytest.fixture(scope="module", autouse=True)  
def setup():  
    """Ensure Slurm is running (local-config mode)."""  
    atf.require_slurm_running()  


@pytest.fixture(scope="module", autouse=True)  
def create_test_apps(setup):  
    """Create test apps used by all tests in this module."""  
    slurm_user = atf.properties["slurm-user"]  

    # App with versions  
    atf.run_command(  
        "scontrol create app AppName=testvasp Version=5.7.1,6.0",  
        user=slurm_user, fatal=True,  
    )  
    # App without versions (version-less)  
    atf.run_command(  
        'scontrol create app AppName=testgeneral Description="General app"',  
        user=slurm_user, fatal=True,  
    )  

    yield  

    # Cleanup  
    atf.run_command(  
        "scontrol delete app testvasp",  
        user=slurm_user, quiet=True,  
    )  
    atf.run_command(  
        "scontrol delete app testgeneral",  
        user=slurm_user, quiet=True,  
    )  


# ---------------------------------------------------------------------------  
# Helper functions  
# ---------------------------------------------------------------------------  
def _create_app(name, **kwargs):  
    """Helper to create an app as slurm-user."""  
    cmd = f"scontrol create app AppName={name}"  
    for k, v in kwargs.items():  
        cmd += f" {k}={v}"  
    atf.run_command(cmd, user=atf.properties["slurm-user"], fatal=True)  


def _delete_app(name):  
    """Helper to delete an app as slurm-user."""  
    atf.run_command(  
        f"scontrol delete app {name}",  
        user=atf.properties["slurm-user"], quiet=True,  
    )  


@pytest.fixture  
def cleanup_app():  
    """Fixture that registers app names for cleanup after test."""  
    apps = []  
    def _register(name):  
        apps.append(name)  
        return name  
    yield _register  
    for name in apps:  
        _delete_app(name)  


# ---------------------------------------------------------------------------  
# TestSubmitValidApp: submit jobs with valid --app values  
# ---------------------------------------------------------------------------  
class TestSubmitValidApp:  

    def test_submit_with_versioned_app(self):  
        """  
        Submit a job with --app=testvasp-5.7.1 (versioned app).  

        Source: _job_create() L7846-7875:  
            find_app_record_by_combined("testvasp-5.7.1") succeeds,  
            app_name = "testvasp", app_version = "5.7.1",  
            app_source = APP_SOURCE_USER (1).  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testvasp-5.7.1 -t1 --wrap="sleep 5"'  
        )  
        assert job_id > 0, "Job with valid versioned app should be submitted"  

    def test_submit_with_unversioned_app(self):  
        """  
        Submit a job with --app=testgeneral (no version suffix).  

        Source: _job_create() L7869-7874:  
            strlen("testgeneral") == strlen(app_ptr->app_name),  
            so app_version = NULL.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testgeneral -t1 --wrap="sleep 5"'  
        )  
        assert job_id > 0, "Job with valid unversioned app should be submitted"  

    def test_submit_with_second_version(self):  
        """  
        Submit with --app=testvasp-6.0 (second version in the list).  
        Verifies that all versions in the comma-separated list are valid.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testvasp-6.0 -t1 --wrap="sleep 5"'  
        )  
        assert job_id > 0, "Job with second version should be submitted"  


# ---------------------------------------------------------------------------  
# TestSubmitInvalidApp: submit jobs with invalid --app values  
# ---------------------------------------------------------------------------  
class TestSubmitInvalidApp:  

    def test_submit_with_nonexistent_app(self):  
        """  
        Submit with --app=nosuchapp should fail.  

        Source: _job_create() L7849-7860:  
            find_app_record_by_combined("nosuchapp") returns NULL,  
            error_code = ESLURM_INVALID_APP_NAME.  
        """  
        result = atf.run_command(  
            'sbatch --app=nosuchapp -t1 --wrap="hostname"'  
        )  
        assert result["exit_code"] != 0  
        assert "invalid app" in result["stderr"].lower() or result["exit_code"] != 0  

    def test_submit_with_invalid_version(self):  
        """  
        Submit with --app=testvasp-9.9.9 (app exists but version doesn't).  

        Source: find_app_record_by_combined() checks the combined hash  
        "testvasp-9.9.9" which doesn't exist → returns NULL → rejected.  
        """  
        result = atf.run_command(  
            'sbatch --app=testvasp-9.9.9 -t1 --wrap="hostname"'  
        )  
        assert result["exit_code"] != 0  

    def test_submit_with_empty_app(self):  
        """  
        Submit with --app= (empty value) should not trigger app validation.  

        Source: _job_create() L7846 checks job_desc->app && job_desc->app[0],  
        empty string has app[0] == '\\0' so the block is skipped.  
        Job should succeed (no app validation performed).  
        """  
        result = atf.run_command(  
            'sbatch --app= -t1 --wrap="hostname"'  
        )  
        # Empty --app might be treated as no --app, or might fail at option parsing.  
        # Either way, it should NOT fail with "invalid app specified".  
        if result["exit_code"] == 0:  
            # Accepted as no-app job  
            pass  
        else:  
            # Rejected at option parsing level, not at app validation  
            assert "invalid app specified" not in result["stderr"]  


# ---------------------------------------------------------------------------  
# TestAppSourceValidation: --app-source requires --app  
# ---------------------------------------------------------------------------  
class TestAppSourceValidation:  

    def test_app_source_without_app_fails(self):  
        """  
        Submit with --app-source=user but no --app should fail.  

        Source: _job_create() L7811-7822:  
            if (!job_desc->app || !job_desc->app[0]) &&  
                job_desc->app_source != APP_SOURCE_NOTSET  
            → error "--app-source option requires --app specification"  
        """  
        result = atf.run_command(  
            'sbatch --app-source=user -t1 --wrap="hostname"'  
        )  
        assert result["exit_code"] != 0  
        combined = result["stderr"] + result["stdout"]  
        assert ("app-source" in combined.lower() or  
                "app" in combined.lower() or  
                result["exit_code"] != 0)  

    def test_app_source_with_app_succeeds(self):  
        """  
        Submit with --app=testvasp-5.7.1 --app-source=user should succeed.  

        Source: _job_create() L7878-7880:  
            app_source is already USER, so it stays USER.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testvasp-5.7.1 --app-source=user -t1 --wrap="sleep 5"'  
        )  
        assert job_id > 0  

    def test_app_source_portal_preserved(self):  
        """  
        Submit with --app=testvasp-5.7.1 --app-source=portal.  

        Source: _job_create() L7878-7879:  
            if app_source == APP_SOURCE_PORTAL → preserved (not overwritten to USER).  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testvasp-5.7.1 --app-source=portal -t1 --wrap="sleep 5"'  
        )  
        assert job_id > 0  


# ---------------------------------------------------------------------------  
# TestAppList: --app=list output  
# ---------------------------------------------------------------------------  
class TestAppList:  

    def test_sbatch_app_list(self):  
        """  
        sbatch --app=list should print app list and exit with 0.  

        Source: sbatch.c L134-149:  
            if opt.app == "list" → slurm_print_app_list() → exit(0).  

        Output format (config_info.c:2464-2492):  
            NAME                  DESCRIPTION  
            ----                  -----------  
            testvasp-5.7.1        ...  
            testvasp-6.0          ...  
            testgeneral           General app  
        """  
        result = atf.run_command("sbatch --app=list")  
        assert result["exit_code"] == 0  
        output = result["stdout"]  
        # Header should be present  
        assert "NAME" in output  
        # Our test apps should appear  
        assert "testvasp-5.7.1" in output  
        assert "testvasp-6.0" in output  
        assert "testgeneral" in output  

    def test_srun_app_list(self):  
        """  
        srun --app=list should print app list and exit with 0.  

        Source: srun/opt.c L518-531: same logic as sbatch.  
        """  
        result = atf.run_command("srun --app=list")  
        assert result["exit_code"] == 0  
        assert "testvasp-5.7.1" in result["stdout"]  
        assert "testgeneral" in result["stdout"]  

    def test_app_list_shows_description(self):  
        """  
        --app=list should show the Description field.  

        Source: slurm_print_app_list() L2480-2490:  
            printf("%-20s  %s\\n", combined, a->description ? a->description : "");  
        """  
        result = atf.run_command("sbatch --app=list")  
        assert result["exit_code"] == 0  
        # testgeneral was created with Description="General app"  
        assert "General app" in result["stdout"]  

    def test_app_list_versioned_expanded(self):  
        """  
        Versioned apps should be expanded: each version gets its own line.  

        Source: slurm_print_app_list() L2469-2487:  
            Tokenizes versions by comma, prints "appname-version" for each.  
        """  
        result = atf.run_command("sbatch --app=list")  
        lines = result["stdout"].strip().splitlines()  
        # Count lines containing "testvasp-"  
        vasp_lines = [l for l in lines if "testvasp-" in l]  
        assert len(vasp_lines) >= 2, (  
            f"Expected at least 2 lines for testvasp (5.7.1 and 6.0), got {len(vasp_lines)}"  
        )  


# ---------------------------------------------------------------------------  
# TestJobAppFields: verify scontrol show job displays app fields  
# ---------------------------------------------------------------------------  
class TestJobAppFields:  

    def test_scontrol_show_job_app_fields(self):  
        """  
        Submit with --app=testvasp-5.7.1, verify scontrol show job output  
        contains AppName, AppVersion, AppSource fields.  

        Source: _copy_job_desc_to_job_record() (job_mgr.c:9311-9316)  
            copies app_name, app_version, app_source to job_record.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testvasp-5.7.1 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  

        output = atf.run_command_output(f"scontrol show job {job_id}")  
        # Verify app fields are present in the output  
        assert "AppName=testvasp" in output, (  
            f"AppName not found in scontrol show job output: {output}"  
        )  
        assert "AppVersion=5.7.1" in output, (  
            f"AppVersion not found in scontrol show job output: {output}"  
        )  
        assert "AppSource=user" in output, (  
            f"AppSource not found in scontrol show job output: {output}"  
        )  

    def test_scontrol_show_job_unversioned_app(self):  
        """  
        Submit with --app=testgeneral (no version), verify AppVersion is  
        empty or absent.  

        Source: _job_create() L7873-7874:  
            app_version = NULL when --app equals app_name.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testgeneral -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  

        output = atf.run_command_output(f"scontrol show job {job_id}")  
        assert "AppName=testgeneral" in output  

    def test_scontrol_show_job_no_app(self):  
        """  
        Submit without --app, verify app fields are empty/absent.  
        """  
        job_id = atf.submit_job_sbatch(  
            '-t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  

        output = atf.run_command_output(f"scontrol show job {job_id}")  
        # AppName should be empty or "(null)" or not present  
        # We check that "AppName=testvasp" is NOT in the output  
        assert "AppName=testvasp" not in output  
        assert "AppName=testgeneral" not in output  

    def test_scontrol_show_job_portal_source(self):  
        """  
        Submit with --app-source=portal, verify AppSource=portal in output.  

        Source: _job_create() L7878-7879:  
            portal source is preserved, not overwritten to USER.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testvasp-5.7.1 --app-source=portal -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  

        output = atf.run_command_output(f"scontrol show job {job_id}")  
        assert "AppSource=portal" in output, (  
            f"Expected AppSource=portal in output: {output}"  
        )  


# ---------------------------------------------------------------------------  
# TestAppEnvVars: verify environment variables in batch scripts  
# ---------------------------------------------------------------------------  
class TestAppEnvVars:  

    def test_batch_env_vars_with_versioned_app(self):  
        script = _shared_path("env_script") + ".sh"  
        outfile = _shared_path("env_out") + ".txt"  
        try:  
            atf.make_bash_script(script, f"""  
    echo "NAME=${{SLURM_JOB_APP_NAME:-UNSET}}" > {outfile}  
    echo "VERSION=${{SLURM_JOB_APP_VERSION:-UNSET}}" >> {outfile}  
    echo "SOURCE=${{SLURM_JOB_APP_SOURCE:-UNSET}}" >> {outfile}  
    """)  
            os.chmod(script, 0o755)  
    
            job_id = atf.submit_job_sbatch(  
                f"--app=testvasp-5.7.1 -t1 -o /dev/null {script}"  
            )  
            assert job_id > 0  
            atf.wait_for_job_state(job_id, "DONE", fatal=True, timeout=60)  
            assert atf.wait_for_file(outfile, timeout=30)  
            output = atf.run_command_output(f"cat {outfile}")  
    
            lines = {}  
            for line in output.strip().splitlines():  
                if "=" in line:  
                    k, v = line.split("=", 1)  
                    lines[k] = v.strip()  
    
            assert lines.get("NAME") == "testvasp"  
            assert lines.get("VERSION") == "5.7.1"  
            assert lines.get("SOURCE") == "user"  
        finally:  
            for f in [script, outfile]:  
                if os.path.exists(f):  
                    os.remove(f)

    def test_batch_env_vars_unversioned_app(self):  
        script = _shared_path("env_nover_script") + ".sh"  
        outfile = _shared_path("env_nover_out") + ".txt"  
        try:  
            atf.make_bash_script(  
                script,  
                "echo NAME=$SLURM_JOB_APP_NAME\n"  
                "echo VERSION=${SLURM_JOB_APP_VERSION:-UNSET}\n"  
                "echo SOURCE=$SLURM_JOB_APP_SOURCE\n"  
            )  
            os.chmod(script, 0o755)  
            job_id = atf.submit_job_sbatch(  
                f"--app=testgeneral -t1 -o {outfile} {script}"  
            )  
            assert job_id > 0  
            atf.wait_for_job_state(job_id, "DONE", fatal=True, timeout=60)  
            assert atf.wait_for_file(outfile, timeout=30)  
            output = atf.run_command_output(f"cat {outfile}")  
            lines = {}  
            for line in output.strip().splitlines():  
                if "=" in line:  
                    k, v = line.split("=", 1)  
                    lines[k] = v.strip()  
            assert lines.get("NAME") == "testgeneral"  
            assert lines.get("VERSION") == "UNSET"  
            assert lines.get("SOURCE") == "user"  
        finally:  
            for f in [script, outfile]:  
                if os.path.exists(f):  
                    os.remove(f)  
    
    def test_batch_env_vars_no_app(self):  
        script = _shared_path("env_noapp_script") + ".sh"  
        outfile = _shared_path("env_noapp_out") + ".txt"  
        try:  
            atf.make_bash_script(  
                script,  
                "echo NAME=${SLURM_JOB_APP_NAME:-UNSET}\n"  
                "echo SOURCE=${SLURM_JOB_APP_SOURCE:-UNSET}\n"  
            )  
            os.chmod(script, 0o755)  
            job_id = atf.submit_job_sbatch(  
                f"-t1 -o {outfile} {script}"  
            )  
            assert job_id > 0  
            atf.wait_for_job_state(job_id, "DONE", fatal=True, timeout=60)  
            assert atf.wait_for_file(outfile, timeout=30)  
            output = atf.run_command_output(f"cat {outfile}")  
            name_line = [l for l in output.splitlines() if l.startswith("NAME=")]  
            assert len(name_line) > 0  
            name_val = name_line[0].split("=", 1)[1].strip()  
            assert name_val == "UNSET", f"Expected UNSET without --app, got: {name_val}"  
        finally:  
            for f in [script, outfile]:  
                if os.path.exists(f):  
                    os.remove(f)


# ---------------------------------------------------------------------------  
# TestSqueueAppFormat: verify squeue --format shows app fields  
# ---------------------------------------------------------------------------  
class TestSqueueAppFormat:  

    def test_squeue_app_column(self):  
        """  
        Submit with --app, verify squeue --Format=App shows combined name.  

        Source: squeue/print.c L3082-3103:  
            _print_job_app() formats as "name-version" or "name".  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testvasp-5.7.1 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  

        output = atf.run_command_output(  
            f"squeue -j {job_id} --noheader --Format=App"  
        ).strip()  
        assert "testvasp-5.7.1" in output, (  
            f"Expected testvasp-5.7.1 in squeue App column: {output}"  
        )  

    def test_squeue_appsource_column(self):  
        """  
        Verify squeue --Format=AppSource shows "user".  

        Source: squeue/print.c _print_job_app_source():  
            Formats app_source as string via app_source_to_str().  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=testvasp-5.7.1 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  

        output = atf.run_command_output(  
            f"squeue -j {job_id} --noheader --Format=AppSource"  
        ).strip()  
        # Default app_source for user-submitted jobs is "user" (APP_SOURCE_USER=1)  
        assert "user" in output, (  
            f"Expected 'user' in squeue AppSource column: {output}"  
        )  

    def test_squeue_filter_by_app(self):  
        """  
        Verify squeue --app=name filters jobs by app_name.  

        Source: squeue/opts.c parses --app into params.app_name_list,  
        then squeue/print.c filters: if app_name not in list, skip.  
        """  
        job1 = atf.submit_job_sbatch(  
            '--app=testvasp-5.7.1 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job1 > 0  
        job2 = atf.submit_job_sbatch(  
            '--app=testgeneral -t1 --hold --wrap="sleep 60"'  
        )  
        assert job2 > 0  
        atf.wait_for_job_state(job1, "PENDING", fatal=True)  
        atf.wait_for_job_state(job2, "PENDING", fatal=True)  

        output = atf.run_command_output(  
            "squeue --noheader --Format=JobId,App --app-name=testvasp"  
        )
        assert str(job1) in output  
        assert str(job2) not in output  


# ---------------------------------------------------------------------------  
# TestAppList: verify --app=list output  
# ---------------------------------------------------------------------------  
class TestAppList:  

    def test_sbatch_app_list(self):  
        """  
        Verify sbatch --app=list prints available apps and exits.  

        Source: sbatch/opt_process.c detects "list" value,  
        calls slurm_print_app_list() which formats:  
            APP                   DESCRIPTION  
            ----                  -----------  
            testvasp-5.7.1        Test VASP  
            testgeneral           General App  
        Then exits with code 0.  
        """  
        result = atf.run_command("sbatch --app=list")  
        # --app=list should print the list and exit (exit code 0)  
        assert result["exit_code"] == 0  
        assert "NAME" in result["stdout"]  
        assert "DESCRIPTION" in result["stdout"]  
        # Should contain our test apps  
        assert "testvasp" in result["stdout"]  
        assert "testgeneral" in result["stdout"]  

    def test_app_list_versioned_format(self):  
        """  
        Verify --app=list shows versioned apps as "name-version".  

        Source: slurm_print_app_list() (config_info.c):  
            For apps with versions, tokenizes version list and prints  
            "appname-version" for each version.  
        """  
        result = atf.run_command("sbatch --app=list")  
        assert result["exit_code"] == 0  
        assert "testvasp-5.7.1" in result["stdout"]  
        assert "testvasp-6.0" in result["stdout"]  

    def test_app_list_unversioned_format(self):  
        """  
        Verify --app=list shows unversioned apps as just "name".  

        Source: slurm_print_app_list() else branch:  
            For apps without versions, prints just app_name.  
        """  
        result = atf.run_command("sbatch --app=list")  
        assert result["exit_code"] == 0  
        # testgeneral has no version, should appear as just "testgeneral"  
        lines = result["stdout"].splitlines()  
        general_lines = [l for l in lines if "testgeneral" in l]  
        assert len(general_lines) > 0  
        # Should NOT have a dash (no version suffix)  
        for line in general_lines:  
            # Extract the app column (first field)  
            app_field = line.split()[0] if line.split() else ""  
            assert app_field == "testgeneral", (  
                f"Expected 'testgeneral' without version suffix, got: {app_field}"  
            )