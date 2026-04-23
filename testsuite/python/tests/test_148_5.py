############################################################################  
# test_148_5.py - Group 5: Environment Variable Injection & Output Display  
#  
# Tests SLURM_JOB_APP_NAME/VERSION/SOURCE env vars, squeue format columns,  
# squeue filtering by --app-source, and scontrol show job app field format.  
############################################################################  
  
import atf  
import os  
import random  
import re  
import string  
import time  
import pytest  
  
  
# ---------------------------------------------------------------------------  
# Shared path helper (compute nodes can access /public/home/slurmtest)  
# ---------------------------------------------------------------------------  
SHARED_DIR = "/public/home/slurmtest"  
  
  
def _shared_path(prefix):  
    tag = ''.join(random.choices(string.ascii_lowercase, k=8))  
    return f"{SHARED_DIR}/{prefix}_{tag}"  
  
  
# ---------------------------------------------------------------------------  
# Helper: create / delete app via scontrol (admin)  
# ---------------------------------------------------------------------------  
def _create_app(name, **kwargs):  
    cmd = f"scontrol create app AppName={name}"  
    for k, v in kwargs.items():  
        cmd += f" {k}={v}"  
    result = atf.run_command(cmd, user=atf.properties["slurm-user"])  
    assert result["exit_code"] == 0, (  
        f"Failed to create app {name}: {result['stderr']}"  
    )  
  
  
def _delete_app(name):  
    atf.run_command(  
        f"scontrol delete app {name}",  
        user=atf.properties["slurm-user"],  
        quiet=True,  
    )  
  
  
# ---------------------------------------------------------------------------  
# Helper: cancel a job quietly  
# ---------------------------------------------------------------------------  
def _cancel_job(job_id):  
    if job_id and job_id > 0:  
        atf.run_command(f"scancel {job_id}", quiet=True)  
  
  
# ---------------------------------------------------------------------------  
# Module-level setup / teardown  
# ---------------------------------------------------------------------------  
# Track all apps and jobs created during this module for cleanup  
_apps_created = []  
_jobs_created = []  
  
  
@pytest.fixture(scope="module", autouse=True)  
def setup():  
    time.sleep(3)
    atf.require_slurm_running()  
  
    # Create test apps  
    _create_app("envapp", Version="1.0,2.0")  
    _apps_created.append("envapp")  
    _create_app("envbare")  # no version  
    _apps_created.append("envbare")  
  
    yield  
  
    # Cleanup: cancel all held jobs, delete all apps  
    for jid in _jobs_created:  
        _cancel_job(jid)  
    for app in _apps_created:  
        _delete_app(app)  
  
  
# ---------------------------------------------------------------------------  
# TestBatchEnvVars: verify SLURM_JOB_APP_* in batch scripts  
# ---------------------------------------------------------------------------  
class TestBatchEnvVars:  
  
    def test_env_versioned_app_user_source(self):  
        """  
        sbatch --app=envapp-1.0 should inject:  
          SLURM_JOB_APP_NAME=envapp  
          SLURM_JOB_APP_VERSION=1.0  
          SLURM_JOB_APP_SOURCE=user  
  
        Source: env.c:1488-1497 env_array_for_batch_job()  
        Source: job_mgr.c:7878-7880 app_source defaults to USER  
        """  
        script = _shared_path("env5_ver_script") + ".sh"  
        outfile = _shared_path("env5_ver_out") + ".txt"  
        try:  
            atf.make_bash_script(script, (  
                f'echo "NAME=${{SLURM_JOB_APP_NAME:-UNSET}}" > {outfile}\n'  
                f'echo "VERSION=${{SLURM_JOB_APP_VERSION:-UNSET}}" >> {outfile}\n'  
                f'echo "SOURCE=${{SLURM_JOB_APP_SOURCE:-UNSET}}" >> {outfile}\n'  
            ))  
            os.chmod(script, 0o755)  
  
            job_id = atf.submit_job_sbatch(  
                f"--app=envapp-1.0 -t1 -o /dev/null {script}"  
            )  
            assert job_id > 0  
            _jobs_created.append(job_id)  
            atf.wait_for_job_state(job_id, "DONE", fatal=True, timeout=60)  
            assert atf.wait_for_file(outfile, timeout=30)  
            output = atf.run_command_output(f"cat {outfile}")  
  
            lines = {}  
            for line in output.strip().splitlines():  
                if "=" in line:  
                    k, v = line.split("=", 1)  
                    lines[k.strip()] = v.strip()  
  
            assert lines.get("NAME") == "envapp", (  
                f"Expected NAME=envapp, got {lines.get('NAME')}"  
            )  
            assert lines.get("VERSION") == "1.0", (  
                f"Expected VERSION=1.0, got {lines.get('VERSION')}"  
            )  
            assert lines.get("SOURCE") == "user", (  
                f"Expected SOURCE=user, got {lines.get('SOURCE')}"  
            )  
        finally:  
            for f in [script, outfile]:  
                if os.path.exists(f):  
                    os.remove(f)  
  
    def test_env_unversioned_app(self):  
        """  
        sbatch --app=envbare (no version) should inject:  
          SLURM_JOB_APP_NAME=envbare  
          SLURM_JOB_APP_VERSION=UNSET (not set because app_version is NULL)  
          SLURM_JOB_APP_SOURCE=user  
  
        Source: env.c:1494 — only sets VERSION if batch->app_version is non-NULL  
        Source: job_mgr.c:7873-7874 — app_version=NULL when no version suffix  
        """  
        script = _shared_path("env5_bare_script") + ".sh"  
        outfile = _shared_path("env5_bare_out") + ".txt"  
        try:  
            atf.make_bash_script(script, (  
                f'echo "NAME=${{SLURM_JOB_APP_NAME:-UNSET}}" > {outfile}\n'  
                f'echo "VERSION=${{SLURM_JOB_APP_VERSION:-UNSET}}" >> {outfile}\n'  
                f'echo "SOURCE=${{SLURM_JOB_APP_SOURCE:-UNSET}}" >> {outfile}\n'  
            ))  
            os.chmod(script, 0o755)  
  
            job_id = atf.submit_job_sbatch(  
                f"--app=envbare -t1 -o /dev/null {script}"  
            )  
            assert job_id > 0  
            _jobs_created.append(job_id)  
            atf.wait_for_job_state(job_id, "DONE", fatal=True, timeout=60)  
            assert atf.wait_for_file(outfile, timeout=30)  
            output = atf.run_command_output(f"cat {outfile}")  
  
            lines = {}  
            for line in output.strip().splitlines():  
                if "=" in line:  
                    k, v = line.split("=", 1)  
                    lines[k.strip()] = v.strip()  
  
            assert lines.get("NAME") == "envbare"  
            # VERSION should be UNSET because app_version is NULL  
            assert lines.get("VERSION") == "UNSET", (  
                f"Expected VERSION=UNSET for unversioned app, got {lines.get('VERSION')}"  
            )  
            assert lines.get("SOURCE") == "user"  
        finally:  
            for f in [script, outfile]:  
                if os.path.exists(f):  
                    os.remove(f)  
  
    def test_env_no_app_submitted(self):  
        """  
        sbatch without --app should NOT inject any SLURM_JOB_APP_* vars.  
  
        Source: env.c:1492 — guard: if (batch->app_name) — skipped when NULL  
        """  
        script = _shared_path("env5_none_script") + ".sh"  
        outfile = _shared_path("env5_none_out") + ".txt"  
        try:  
            atf.make_bash_script(script, (  
                f'echo "NAME=${{SLURM_JOB_APP_NAME:-UNSET}}" > {outfile}\n'  
                f'echo "VERSION=${{SLURM_JOB_APP_VERSION:-UNSET}}" >> {outfile}\n'  
                f'echo "SOURCE=${{SLURM_JOB_APP_SOURCE:-UNSET}}" >> {outfile}\n'  
            ))  
            os.chmod(script, 0o755)  
  
            job_id = atf.submit_job_sbatch(  
                f"-t1 -o /dev/null {script}"  
            )  
            assert job_id > 0  
            _jobs_created.append(job_id)  
            atf.wait_for_job_state(job_id, "DONE", fatal=True, timeout=60)  
            assert atf.wait_for_file(outfile, timeout=30)  
            output = atf.run_command_output(f"cat {outfile}")  
  
            lines = {}  
            for line in output.strip().splitlines():  
                if "=" in line:  
                    k, v = line.split("=", 1)  
                    lines[k.strip()] = v.strip()  
  
            assert lines.get("NAME") == "UNSET", (  
                f"Expected NAME=UNSET without --app, got {lines.get('NAME')}"  
            )  
            assert lines.get("VERSION") == "UNSET"  
            assert lines.get("SOURCE") == "UNSET"  
        finally:  
            for f in [script, outfile]:  
                if os.path.exists(f):  
                    os.remove(f)  
  
    def test_env_portal_source_preserved(self):  
        """  
        sbatch --app=envapp-1.0 --app-source=portal should inject:  
          SLURM_JOB_APP_SOURCE=portal  
  
        Source: job_mgr.c:7878-7880 — portal/marketplace are preserved,  
                not overwritten to USER.  
        Source: env.c:1496 — app_source_to_str(APP_SOURCE_PORTAL) = "portal"  
        """  
        script = _shared_path("env5_portal_script") + ".sh"  
        outfile = _shared_path("env5_portal_out") + ".txt"  
        try:  
            atf.make_bash_script(script, (  
                f'echo "SOURCE=${{SLURM_JOB_APP_SOURCE:-UNSET}}" > {outfile}\n'  
            ))  
            os.chmod(script, 0o755)  
  
            job_id = atf.submit_job_sbatch(  
                f"--app=envapp-1.0 --app-source=portal -t1 -o /dev/null {script}"  
            )  
            assert job_id > 0  
            _jobs_created.append(job_id)  
            atf.wait_for_job_state(job_id, "DONE", fatal=True, timeout=60)  
            assert atf.wait_for_file(outfile, timeout=30)  
            output = atf.run_command_output(f"cat {outfile}")  
  
            lines = {}  
            for line in output.strip().splitlines():  
                if "=" in line:  
                    k, v = line.split("=", 1)  
                    lines[k.strip()] = v.strip()  
  
            assert lines.get("SOURCE") == "portal", (  
                f"Expected SOURCE=portal, got {lines.get('SOURCE')}"  
            )  
        finally:  
            for f in [script, outfile]:  
                if os.path.exists(f):  
                    os.remove(f)  
  
  
# ---------------------------------------------------------------------------  
# TestSqueueAppSourceFilter: verify squeue --app-source filtering  
# ---------------------------------------------------------------------------  
class TestSqueueAppSourceFilter:  
  
    def test_filter_by_app_source_user(self):  
        """  
        squeue --app-source=user should only show jobs with app_source=USER.  
  
        Source: print.c:157-175 — iterates app_source_list, matches  
                jobs[i].app_source against each value.  
        """  
        # Submit a job with --app (source=user)  
        job_with_app = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_with_app > 0  
        _jobs_created.append(job_with_app)  
  
        # Submit a job without --app (source=notset)  
        job_no_app = atf.submit_job_sbatch(  
            '-t1 --hold --wrap="sleep 60"'  
        )  
        assert job_no_app > 0  
        _jobs_created.append(job_no_app)  
  
        atf.wait_for_job_state(job_with_app, "PENDING", fatal=True)  
        atf.wait_for_job_state(job_no_app, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue --app-source=user --noheader --Format=JobID"  
        ).strip()  
  
        assert str(job_with_app) in output, (  
            f"Job {job_with_app} with app should appear in --app-source=user filter"  
        )  
        assert str(job_no_app) not in output, (  
            f"Job {job_no_app} without app should NOT appear in --app-source=user filter"  
        )  
  
    def test_filter_by_app_source_portal(self):  
        """  
        squeue --app-source=portal should only show jobs with app_source=PORTAL.  
  
        Source: print.c:166 — *src_val == jobs[i].app_source  
        """  
        job_portal = atf.submit_job_sbatch(  
            '--app=envapp-2.0 --app-source=portal -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_portal > 0  
        _jobs_created.append(job_portal)  
  
        job_user = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_user > 0  
        _jobs_created.append(job_user)  
  
        atf.wait_for_job_state(job_portal, "PENDING", fatal=True)  
        atf.wait_for_job_state(job_user, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue --app-source=portal --noheader --Format=JobID"  
        ).strip()  
  
        assert str(job_portal) in output, (  
            f"Portal job {job_portal} should appear in --app-source=portal filter"  
        )  
        assert str(job_user) not in output, (  
            f"User job {job_user} should NOT appear in --app-source=portal filter"  
        )  
  
    def test_combined_app_name_and_source_filter(self):  
        """  
        squeue --app-name=envapp --app-source=user should only show jobs  
        matching BOTH app_name=envapp AND app_source=user.  
  
        Source: print.c:157-194 — both filters applied sequentially.  
        """  
        job_match = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_match > 0  
        _jobs_created.append(job_match)  
  
        job_diff_name = atf.submit_job_sbatch(  
            '--app=envbare -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_diff_name > 0  
        _jobs_created.append(job_diff_name)  
  
        atf.wait_for_job_state(job_match, "PENDING", fatal=True)  
        atf.wait_for_job_state(job_diff_name, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            "squeue --app-name=envapp --app-source=user "  
            "--noheader --Format=JobID"  
        ).strip()  
  
        assert str(job_match) in output, (  
            f"Job {job_match} should match both filters"  
        )  
        assert str(job_diff_name) not in output, (  
            f"Job {job_diff_name} (envbare) should NOT match --app-name=envapp"  
        )  
  
  
# ---------------------------------------------------------------------------  
# TestSqueueColumns: verify squeue --Format column output  
# ---------------------------------------------------------------------------  
class TestSqueueColumns:  
  
    def test_app_column_header(self):  
        """  
        squeue --Format=App should print header "APP".  
  
        Source: print.c:3087 — _print_str("APP", ...)  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue -j {job_id} --Format=App"  
        )  
        # First line should contain the header "APP"  
        first_line = output.strip().splitlines()[0] if output.strip() else ""  
        assert "APP" in first_line, (  
            f"Expected 'APP' header, got: {first_line}"  
        )  
  
    def test_appsource_column_header(self):  
        """  
        squeue --Format=AppSource should print header "APPSOURCE".  
  
        Source: print.c:3108 — _print_str("APPSOURCE", ...)  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue -j {job_id} --Format=AppSource"  
        )  
        first_line = output.strip().splitlines()[0] if output.strip() else ""  
        assert "APPSOURCE" in first_line, (  
            f"Expected 'APPSOURCE' header, got: {first_line}"  
        )  
  
    def test_app_column_versioned(self):  
        """  
        squeue --Format=App for a versioned app should show "name-version".  
  
        Source: print.c:3091-3093 — xstrfmtcat(app_str, "%s-%s", ...)  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envapp-2.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue -j {job_id} --noheader --Format=App"  
        ).strip()  
        assert "envapp-2.0" in output, (  
            f"Expected 'envapp-2.0' in App column, got: {output}"  
        )  
  
    def test_app_column_unversioned(self):  
        """  
        squeue --Format=App for an unversioned app should show just "name".  
  
        Source: print.c:3094-3095 — app_str = xstrdup(job->app_name)  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envbare -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue -j {job_id} --noheader --Format=App"  
        ).strip()  
        assert "envbare" in output, (  
            f"Expected 'envbare' in App column, got: {output}"  
        )  
        # Should NOT contain a dash (no version)  
        assert "envbare-" not in output, (  
            f"Unversioned app should not have dash suffix: {output}"  
        )  
  
    def test_app_column_empty_for_no_app_job(self):  
        """  
        squeue --Format=App for a job without --app should show empty.  
  
        Source: print.c:3090 — guard: if (job->app_name && job->app_name[0])  
                Falls through to _print_str("", ...) at line 3097.  
        """  
        job_id = atf.submit_job_sbatch(  
            '-t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue -j {job_id} --noheader --Format=App"  
        ).strip()  
        # Should be empty or whitespace only  
        assert output == "" or output.isspace() or "envapp" not in output, (  
            f"Expected empty App column for no-app job, got: '{output}'"  
        )  
  
    def test_appsource_column_empty_for_no_app_job(self):  
        """  
        squeue --Format=AppSource for a job without --app should show empty.  
  
        Source: print.c:3110-3114 — guard: if (job->app_name && job->app_name[0])  
                else _print_str("", ...)  
        """  
        job_id = atf.submit_job_sbatch(  
            '-t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue -j {job_id} --noheader --Format=AppSource"  
        ).strip()  
        assert output == "" or output.isspace() or "user" not in output, (  
            f"Expected empty AppSource for no-app job, got: '{output}'"  
        )  
  
    def test_appsource_shows_user(self):  
        """  
        squeue --Format=AppSource for --app job should show "user".  
  
        Source: print.c:3111 — app_source_to_str(job->app_source)  
        Source: slurm_protocol_defs.c:4338 — APP_SOURCE_USER -> "user"  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue -j {job_id} --noheader --Format=AppSource"  
        ).strip()  
        assert "user" in output, (  
            f"Expected 'user' in AppSource column, got: '{output}'"  
        )  
  
    def test_appsource_shows_portal(self):  
        """  
        squeue --Format=AppSource for --app-source=portal should show "portal".  
  
        Source: slurm_protocol_defs.c:4340 — APP_SOURCE_PORTAL -> "portal"  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envapp-1.0 --app-source=portal -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            f"squeue -j {job_id} --noheader --Format=AppSource"  
        ).strip()  
        assert "portal" in output, (  
            f"Expected 'portal' in AppSource column, got: '{output}'"  
        )  
  
    def test_squeue_filter_by_app_name(self):  
        """  
        squeue --app-name=envapp should only show jobs with that app_name.  
  
        Source: print.c:176-194 — filter by params.app_name_list,  
                compares job->app_name with each entry via xstrcasecmp.  
        """  
        job_with_app = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_with_app > 0  
        _jobs_created.append(job_with_app)  
  
        job_without_app = atf.submit_job_sbatch(  
            '-t1 --hold --wrap="sleep 60"'  
        )  
        assert job_without_app > 0  
        _jobs_created.append(job_without_app)  
  
        atf.wait_for_job_state(job_with_app, "PENDING", fatal=True)  
        atf.wait_for_job_state(job_without_app, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            "squeue --app-name=envapp --noheader --Format=JobID"  
        ).strip()  
        assert str(job_with_app) in output, (  
            f"Expected job {job_with_app} in filtered output: '{output}'"  
        )  
        assert str(job_without_app) not in output, (  
            f"Job {job_without_app} (no app) should not appear in filtered output: '{output}'"  
        )  
  
    def test_squeue_filter_by_app_source(self):  
        """  
        squeue --app-source=portal should only show jobs with that source.  
  
        Source: print.c — filter by params.app_source_list,  
                compares job->app_source with each entry.  
        """  
        job_user = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_user > 0  
        _jobs_created.append(job_user)  
  
        job_portal = atf.submit_job_sbatch(  
            '--app=envapp-1.0 --app-source=portal -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_portal > 0  
        _jobs_created.append(job_portal)  
  
        atf.wait_for_job_state(job_user, "PENDING", fatal=True)  
        atf.wait_for_job_state(job_portal, "PENDING", fatal=True)  
  
        output = atf.run_command_output(  
            "squeue --app-source=portal --noheader --Format=JobID"  
        ).strip()  
        assert str(job_portal) in output, (  
            f"Expected job {job_portal} in portal-filtered output: '{output}'"  
        )  
        assert str(job_user) not in output, (  
            f"Job {job_user} (source=user) should not appear in portal filter: '{output}'"  
        )  
  
  
# ---------------------------------------------------------------------------  
# TestScontrolShowJobApp: scontrol show job app fields  
# ---------------------------------------------------------------------------  
class TestScontrolShowJobApp:  
  
    def test_show_job_app_name(self):  
        """  
        scontrol show job should display AppName= field.  
  
        Source: job_info.c — sprint_job_info() outputs AppName=<value>.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(f"scontrol show job {job_id}")  
        assert "AppName=envapp" in output, (  
            f"Expected AppName=envapp in scontrol output: '{output}'"  
        )  
  
    def test_show_job_app_version(self):  
        """  
        scontrol show job should display AppVersion= field.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envapp-1.0 -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(f"scontrol show job {job_id}")  
        assert "AppVersion=1.0" in output, (  
            f"Expected AppVersion=1.0 in scontrol output: '{output}'"  
        )  
  
    def test_show_job_app_source(self):  
        """  
        scontrol show job should display AppSource= field.  
        """  
        job_id = atf.submit_job_sbatch(  
            '--app=envapp-1.0 --app-source=portal -t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(f"scontrol show job {job_id}")  
        assert "AppSource=portal" in output, (  
            f"Expected AppSource=portal in scontrol output: '{output}'"  
        )  
  
    def test_show_job_no_app(self):  
        """  
        scontrol show job without --app should show empty or absent app fields.  
        """  
        job_id = atf.submit_job_sbatch(  
            '-t1 --hold --wrap="sleep 60"'  
        )  
        assert job_id > 0  
        _jobs_created.append(job_id)  
        atf.wait_for_job_state(job_id, "PENDING", fatal=True)  
  
        output = atf.run_command_output(f"scontrol show job {job_id}")  
        # AppName should be empty or "(null)" or not present  
        if "AppName=" in output:  
            # Extract value after AppName=  
            for line in output.splitlines():  
                if "AppName=" in line:  
                    # AppName should be empty  
                    idx = line.index("AppName=") + len("AppName=")  
                    val = line[idx:].split()[0] if idx < len(line) else ""  
                    assert val == "" or val == "(null)" or val.startswith(" "), (  
                        f"Expected empty AppName for no-app job, got: '{val}'"  
                    )