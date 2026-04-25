############################################################################  
# test_148_6.py - Group 6: App State Persistence & Reconfigure  
#  
# Tests the behavior of dynamically created apps across scontrol reconfigure  
# and slurmctld restart, with and without ReconfigFlags=KeepAppInfo.  
#  
# Key code paths tested:  
#   read_slurm_conf() L3334-3448: reconfig_flags initialization and app loading  
#   load_all_app_state() L1804-1950: state file merge logic  
#   init_app_conf() L1381-1400: app subsystem reset on reconfigure  
#   dump_all_app_state() L1687-1767: state file serialization  
#  
# IMPORTANT: reconfig_flags is captured from slurm_conf.reconfig_flags  
# BEFORE _init_all_slurm_conf() re-parses slurm.conf (line 3356).  
# This means changing ReconfigFlags in slurm.conf requires TWO reconfigures:  
#   1st reconfigure: loads new ReconfigFlags into slurm_conf.reconfig_flags  
#   2nd reconfigure: uses the now-in-memory KeepAppInfo flag  
############################################################################  
import atf  
import pytest  
import time  
import os  
import re  
  
  
# ---------------------------------------------------------------------------  
# Module-level helpers  
# ---------------------------------------------------------------------------  
  
_SLURM_USER = None  
_CONF_DIR = None  
_SBIN_DIR = None  
_CONF_FILE = None  
_CONF_BACKUP = None  
  
  
def _get_conf_file():  
    global _CONF_FILE  
    if _CONF_FILE is None:  
        _CONF_FILE = f"{atf.properties['slurm-config-dir']}/slurm.conf"  
    return _CONF_FILE  
  
  
def _slurm_user():  
    global _SLURM_USER  
    if _SLURM_USER is None:  
        _SLURM_USER = atf.properties["slurm-user"]  
    return _SLURM_USER  
  
  
def _sbin_dir():  
    global _SBIN_DIR  
    if _SBIN_DIR is None:  
        _SBIN_DIR = atf.properties["slurm-sbin-dir"]  
    return _SBIN_DIR  
  
  
def _backup_conf():  
    """Backup slurm.conf to slurm.conf.test_bak"""  
    global _CONF_BACKUP  
    conf = _get_conf_file()  
    _CONF_BACKUP = conf + ".test_148_6_bak"  
    atf.run_command(  
        f"cp {conf} {_CONF_BACKUP}",  
        user=_slurm_user(), fatal=True  
    )  
  
  
def _restore_conf():  
    """Restore slurm.conf from backup"""  
    global _CONF_BACKUP  
    if _CONF_BACKUP and os.path.exists(_CONF_BACKUP):  
        conf = _get_conf_file()  
        atf.run_command(  
            f"cp {_CONF_BACKUP} {conf}",  
            user=_slurm_user(), fatal=True  
        )  
        atf.run_command(  
            f"rm -f {_CONF_BACKUP}",  
            user=_slurm_user()  
        )  
        _CONF_BACKUP = None  
  
  
def _reconfigure():  
    """Run scontrol reconfigure and wait briefly for it to take effect."""  
    result = atf.run_command(  
        "scontrol reconfigure",  
        user=_slurm_user()  
    )  
    assert result["exit_code"] == 0, (  
        f"scontrol reconfigure failed: {result['stderr']}"  
    )  
    time.sleep(2)  
  
  
def _create_app(name, **kwargs):  
    """Create an app via scontrol."""  
    cmd = f"scontrol create app AppName={name}"  
    for k, v in kwargs.items():  
        cmd += f" {k}={v}"  
    result = atf.run_command(cmd, user=_slurm_user())  
    assert result["exit_code"] == 0, (  
        f"Failed to create app {name}: {result['stderr']}"  
    )  
  
  
def _delete_app(name):  
    """Delete an app via scontrol (ignore errors if not found)."""  
    atf.run_command(  
        f"scontrol delete app={name}",  
        user=_slurm_user(),  
        fatal=False,  
    )  
  
  
def _show_app(name):
    return atf.run_command(
        f"scontrol show app {name}",
        user=_slurm_user(),
    )


def _get_current_reconfig_flags():  
    output = atf.run_command_output(  
        "scontrol show config | grep -i ReconfigFlags"  
    ).strip()  
    if "=" in output:  
        val = output.split("=", 1)[1].strip()  
        if val == "(null)" or val == "":  
            return ""  
        return val  
    return ""
  
  
def _has_keep_app_info():  
    flags = _get_current_reconfig_flags()  
    if not flags or flags == "(null)":  
        return False  
    return "keepappinfo" in flags.lower()
  
  
def _set_reconfig_flags_in_conf(flags_value):  
    """Set ReconfigFlags in slurm.conf. Pass None or '' to remove."""  
    conf = _get_conf_file()  
    # Remove existing ReconfigFlags line  
    atf.run_command(  
        f"sed -i '/^[[:space:]]*ReconfigFlags/d' {conf}",  
        user=_slurm_user(), fatal=True  
    )  
    # Add new line if value is provided  
    if flags_value:  
        atf.run_command(  
            f"echo 'ReconfigFlags={flags_value}' >> {conf}",  
            user=_slurm_user(), fatal=True  
        )  
  
  
def _add_app_to_conf(app_name, version=None, description=None):  
    """Add an AppName line to slurm.conf."""  
    conf = _get_conf_file()  
    line = f"AppName={app_name}"  
    if version:  
        line += f" version={version}"  
    if description:  
        line += f' Description="{description}"'  
    atf.run_command(  
        f"echo '{line}' >> {conf}",  
        user=_slurm_user(), fatal=True  
    )  
  
  
def _remove_app_from_conf(app_name):  
    """Remove AppName=<name> line from slurm.conf."""  
    conf = _get_conf_file()  
    atf.run_command(  
        f"sed -i '/^[[:space:]]*AppName={app_name}/d' {conf}",  
        user=_slurm_user(), fatal=True  
    )  
  
  
def _wait_for_slurmctld_up(timeout=60):  
    """Wait for slurmctld to respond to ping."""  
    for _ in range(timeout):  
        result = atf.run_command("scontrol ping", quiet=True)  
        if "is UP" in result.get("stdout", ""):  
            return True  
        time.sleep(1)  
    return False  
  
  
def _wait_for_slurmctld_down(timeout=30):  
    """Wait for slurmctld to stop responding."""  
    for _ in range(timeout):  
        result = atf.run_command("scontrol ping", quiet=True)  
        if "is UP" not in result.get("stdout", ""):  
            return True  
        time.sleep(1)  
    return False  
  
  
def _stop_slurmctld():  
    """Stop slurmctld via scontrol shutdown."""  
    atf.run_command(  
        "scontrol shutdown slurmctld",  
        user=_slurm_user()  
    )  
    assert _wait_for_slurmctld_down(), "slurmctld did not stop in time"  
    time.sleep(2)  
  
  
def _start_slurmctld(full_recovery=False, ignore_state_errors=False):
    """Start slurmctld.

    full_recovery=True       -> add -R (recover > 1)
    ignore_state_errors=True -> add -i (skip fatal on corrupt state files,
                                consistent with native Slurm behavior for
                                load_all_{part,node,job}_state).
    """
    cmd = f"{_sbin_dir()}/slurmctld"
    if full_recovery:
        cmd += " -R"
    if ignore_state_errors:
        cmd += " -i"
    atf.run_command(cmd, user=_slurm_user())
    assert _wait_for_slurmctld_up(), (
        f"slurmctld did not start in time (cmd: {cmd})"
    )
    time.sleep(2)  


def _get_state_save_location():
    """Get StateSaveLocation from scontrol show config."""
    output = atf.run_command_output(
        "scontrol show config | grep -i StateSaveLocation"
    ).strip()
    if "=" in output:
        return output.split("=", 1)[1].strip()
    return None


def _get_app_state_file():
    """Return absolute path to <StateSaveLocation>/app_state."""
    loc = _get_state_save_location()
    if not loc:
        return None
    return f"{loc}/app_state"  
  
  
# ---------------------------------------------------------------------------  
# Module setup/teardown  
# ---------------------------------------------------------------------------  
  
@pytest.fixture(scope="module", autouse=True)  
def setup():  
    """Ensure Slurm is running and backup slurm.conf."""  
    atf.require_slurm_running()  
    _backup_conf()  
  
    yield  
  
    # Restore original slurm.conf and reconfigure  
    _restore_conf()  
    # Ensure slurmctld is running  
    if not _wait_for_slurmctld_up(timeout=5):  
        _start_slurmctld()  
    else:  
        _reconfigure()  
    # Clean up any leftover test apps  
    for name in ["dynapp6a", "dynapp6b", "dynapp6c", "dynapp6d",  
                  "dynapp6e", "dynapp6f", "confapp6a", "confapp6b",  
                  "dynapp6r1", "dynapp6r2"]:  
        _delete_app(name)  
  
  
# ---------------------------------------------------------------------------  
# TestReconfigWithoutKeepAppInfo  
# ---------------------------------------------------------------------------  
  
class TestReconfigWithoutKeepAppInfo:  
    """  
    Verify that dynamic apps are LOST on scontrol reconfigure  
    when ReconfigFlags does NOT include KeepAppInfo.  
  
    Source: read_slurm_conf() L3356: reconfig_flags = slurm_conf.reconfig_flags  
    Source: load_all_app_state() L1817: if !(RECONFIG_KEEP_APP_INFO) → skip  
    Source: L1819: schedule_app_save() → overwrites state file with config-only apps  
    """  
  
    def _ensure_no_keep_app_info(self):  
        """Ensure KeepAppInfo is NOT in the in-memory ReconfigFlags.  
  
        Because reconfig_flags is captured from the PREVIOUS config,  
        we need to:  
        1. Remove KeepAppInfo from slurm.conf  
        2. Reconfigure once (loads new config into memory)  
        3. Now the in-memory reconfig_flags no longer has KeepAppInfo  
        """  
        if _has_keep_app_info():  
            current = _get_current_reconfig_flags()  
            parts = [p.strip() for p in current.split(",")  
                     if p.strip().lower() != "keepappinfo"]  
            new_flags = ",".join(parts) if parts else ""  
            _set_reconfig_flags_in_conf(new_flags if new_flags else "")  
            # Reconfigure to load the new flags into memory  
            atf.run_command(  
                "scontrol reconfigure",  
                user=atf.properties["slurm-user"],  
                fatal=True,  
            )  
            import time  
            time.sleep(2)  
  
    def test_dynamic_app_lost_on_reconfigure(self):  
        """  
        Dynamic app is LOST after scontrol reconfigure without KeepAppInfo.  
  
        Flow:  
        1. Ensure KeepAppInfo is NOT in memory (may need a preliminary reconfigure)  
        2. Create dynamic app  
        3. scontrol reconfigure  
        4. show app → not found  
  
        Source: read_slurm_conf() L3356: reconfig_flags = slurm_conf.reconfig_flags (old value)  
        Source: load_all_app_state() L1817: !(RECONFIG_KEEP_APP_INFO) → skip state file  
        Source: L1819: schedule_app_save() → overwrites state file  
        """  
        self._ensure_no_keep_app_info()  
  
        _create_app("dynlost1", version="1.0")  
        show = _show_app("dynlost1")  
        assert "AppName=dynlost1" in show["stdout"], "App should exist before reconfigure"  
  
        atf.run_command(  
            "scontrol reconfigure",  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
        import time  
        time.sleep(3)  
  
        show = _show_app("dynlost1")  
        assert "No app" in show["stdout"], (  
            "Dynamic app should be LOST after reconfigure without KeepAppInfo"  
        )  
  
    def test_config_app_survives_reconfigure_without_keep(self):  
        """  
        Apps defined in slurm.conf survive reconfigure even without KeepAppInfo.  
  
        Source: _build_all_app_info() always rebuilds from slurm.conf.  
        Dynamic apps are lost, but config-defined apps are re-created.  
        """  
        self._ensure_no_keep_app_info()  
  
        app_name = "confapp_nokeep"  
        _add_app_to_conf(app_name, version="1.0")  
        try:  
            atf.run_command(  
                "scontrol reconfigure",  
                user=atf.properties["slurm-user"],  
                fatal=True,  
            )  
            import time  
            time.sleep(3)  
  
            show = _show_app(app_name)  
            assert f"AppName={app_name}" in show["stdout"], (  
                "Config-defined app should survive reconfigure"  
            )  
        finally:  
            _remove_app_from_conf(app_name)  
            atf.run_command(  
                "scontrol reconfigure",  
                user=atf.properties["slurm-user"],  
                quiet=True,  
            )  
  
  
# ---------------------------------------------------------------------------  
# TestReconfigWithKeepAppInfo  
# ---------------------------------------------------------------------------  
  
class TestReconfigWithKeepAppInfo:  
    """  
    Verify that dynamic apps are PRESERVED on scontrol reconfigure  
    when ReconfigFlags includes KeepAppInfo.  
  
    Source: read_slurm_conf() L3356: reconfig_flags = slurm_conf.reconfig_flags  
    Source: load_all_app_state() L1822+: RECONFIG_KEEP_APP_INFO set → load state file  
    Source: L1838-1870: merge state file records into config-loaded app_list  
    """  
  
    def _ensure_keep_app_info(self):  
        """Ensure KeepAppInfo IS in the in-memory ReconfigFlags.  
  
        1. Add KeepAppInfo to slurm.conf ReconfigFlags  
        2. Reconfigure once to load it into memory  
        3. Now the in-memory reconfig_flags includes KeepAppInfo  
        """  
        if not _has_keep_app_info():  
            current = _get_current_reconfig_flags()  
            if current:  
                new_flags = current + ",KeepAppInfo"  
            else:  
                new_flags = "KeepAppInfo"  
            _set_reconfig_flags_in_conf(new_flags)  
            atf.run_command(  
                "scontrol reconfigure",  
                user=atf.properties["slurm-user"],  
                fatal=True,  
            )  
            import time  
            time.sleep(2)  
  
    def test_dynamic_app_preserved_on_reconfigure(self):  
        """  
        Dynamic app is PRESERVED after reconfigure with KeepAppInfo.  
  
        Source: load_all_app_state() L1838-1870:  
            For each record in state file, if app_name not in app_list,  
            create a new app_record and add to app_list + hash tables.  
        """  
        self._ensure_keep_app_info()  
  
        _create_app("dynkeep1", version="2.0")  
        show = _show_app("dynkeep1")  
        assert "AppName=dynkeep1" in show["stdout"]  
  
        atf.run_command(  
            "scontrol reconfigure",  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
        import time  
        time.sleep(3)  
  
        show = _show_app("dynkeep1")  
        assert "AppName=dynkeep1" in show["stdout"], (  
            "Dynamic app should be PRESERVED after reconfigure with KeepAppInfo"  
        )  
        assert "2.0" in show["stdout"], (  
            "Version should be preserved"  
        )  
  
        # Cleanup  
        _delete_app("dynkeep1")  
  
    def test_dynamic_app_version_preserved(self):  
        """  
        Dynamic app's updated version is preserved after reconfigure with KeepAppInfo.  
  
        Source: load_all_app_state() L1849-1856:  
            State file record's versions, description, watchdog, default_flag  
            are all restored into the new app_record.  
        """  
        self._ensure_keep_app_info()  
  
        _create_app("dynkeep2", version="1.0")  
        atf.run_command(  
            "scontrol update app AppName=dynkeep2 Version+=2.0",  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
        show_before = _show_app("dynkeep2")  
        assert "1.0" in show_before["stdout"]  
        assert "2.0" in show_before["stdout"]  
  
        atf.run_command(  
            "scontrol reconfigure",  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
        import time  
        time.sleep(3)  
  
        show_after = _show_app("dynkeep2")  
        assert "AppName=dynkeep2" in show_after["stdout"], "App should still exist"  
        assert "1.0" in show_after["stdout"], "Version 1.0 should be preserved"  
        assert "2.0" in show_after["stdout"], "Version 2.0 should be preserved"  
  
        # Cleanup  
        _delete_app("dynkeep2")  
  
    def test_config_and_dynamic_apps_coexist(self):  
        """  
        After reconfigure with KeepAppInfo, both config-defined and  
        dynamic apps should exist.  
  
        Source: _build_all_app_info() loads config apps first,  
        then load_all_app_state() merges dynamic apps from state file.  
        State file records whose app_name already exists in app_list  
        are skipped (L1842-1845).  
        """  
        self._ensure_keep_app_info()  
  
        conf_app = "confcoexist"  
        _add_app_to_conf(conf_app, version="1.0")  
        try:  
            atf.run_command(  
                "scontrol reconfigure",  
                user=atf.properties["slurm-user"],  
                fatal=True,  
            )  
            import time  
            time.sleep(2)  
  
            # Now create a dynamic app  
            _create_app("dyncoexist", version="3.0")  
  
            # Reconfigure again  
            atf.run_command(  
                "scontrol reconfigure",  
                user=atf.properties["slurm-user"],  
                fatal=True,  
            )  
            time.sleep(3)  
  
            # Both should exist  
            show_conf = _show_app(conf_app)  
            assert f"AppName={conf_app}" in show_conf["stdout"], (  
                "Config app should exist after reconfigure"  
            )  
  
            show_dyn = _show_app("dyncoexist")  
            assert "AppName=dyncoexist" in show_dyn["stdout"], (  
                "Dynamic app should exist after reconfigure with KeepAppInfo"  
            )  
  
            # Cleanup dynamic app  
            _delete_app("dyncoexist")  
        finally:  
            _remove_app_from_conf(conf_app)  
            atf.run_command(  
                "scontrol reconfigure",  
                user=atf.properties["slurm-user"],  
                quiet=True,  
            )  
  
  
# ---------------------------------------------------------------------------  
# TestReconfigFlagsEdgeCases  
# ---------------------------------------------------------------------------  
  
class TestReconfigFlagsEdgeCases:  
    """  
    Edge cases for ReconfigFlags and app state persistence.  
    """  
  
    def test_state_file_overwritten_on_reconfigure_without_keep(self):  
        """  
        After reconfigure without KeepAppInfo, the state file is overwritten  
        with config-only apps, so a subsequent slurmctld -R also won't  
        recover the dynamic app.  
  
        Source: load_all_app_state() L1819: schedule_app_save()  
            When skipping state file load, it immediately schedules a save,  
            which overwrites the state file with current (config-only) app_list.  
        """  
        # Ensure no KeepAppInfo  
        if _has_keep_app_info():  
            current = _get_current_reconfig_flags()  
            parts = [p.strip() for p in current.split(",")  
                     if p.strip().lower() != "keepappinfo"]  
            _set_reconfig_flags_in_conf(",".join(parts) if parts else "")  
            atf.run_command(  
                "scontrol reconfigure",  
                user=atf.properties["slurm-user"],  
                fatal=True,  
            )  
            import time  
            time.sleep(2)  
  
        _create_app("statelost1", version="1.0")  
  
        # Reconfigure without KeepAppInfo → state file overwritten  
        atf.run_command(  
            "scontrol reconfigure",  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
        import time  
        time.sleep(3)  
  
        # App should be gone  
        show = _show_app("statelost1")  
        assert "No app" in show["stdout"], (  
            "Dynamic app should be lost after reconfigure"  
        )  
  
        # Even show all apps should not contain it  
        show_all = atf.run_command(  
            "scontrol show app",  
            user=atf.properties["slurm-user"],  
        )  
        assert "statelost1" not in show_all["stdout"], (  
            "Dynamic app should not appear in any app listing"  
        )


# ---------------------------------------------------------------------------
# TestStateFileEdgeCases
# ---------------------------------------------------------------------------

class TestStateFileEdgeCases:
    """
    Edge cases for state file handling: corruption, missing file, version
    mismatch, and dump-time disk failure. These tests ensure slurmctld does
    not coredump and original Slurm flow is not blocked when the app_state
    file is in an unexpected state.

    Source: load_all_app_state() L1842-1950 (state file open/parse/merge)
    Source: dump_all_app_state() L1725-1805 (atomic write via .new -> rename)
    """

    def _ensure_keep_app_info(self):
        """Ensure KeepAppInfo is in memory so state file is loaded on restart."""
        if not _has_keep_app_info():
            current = _get_current_reconfig_flags()
            new_flags = (current + ",KeepAppInfo") if current else "KeepAppInfo"
            _set_reconfig_flags_in_conf(new_flags)
            atf.run_command(
                "scontrol reconfigure",
                user=_slurm_user(),
                fatal=True,
            )
            time.sleep(2)

    def test_corrupt_state_file_handled(self):
        """
        Manually corrupt spool/app_state. With slurmctld -i, the controller
        must start (no coredump) and degrade gracefully.

        Native Slurm behavior: load_all_{part,node,job}_state all call
        fatal() on version mismatch unless ignore_state_errors (-i) is set.
        load_all_app_state() follows the same pattern at L1883-1894.
        """
        state_file = _get_app_state_file()
        if not state_file:
            pytest.skip("Cannot determine StateSaveLocation")

        self._ensure_keep_app_info()

        # Create a dynamic app and force a dump so app_state exists
        _create_app("corrupt_pre", version="1.0")
        time.sleep(2)

        _stop_slurmctld()

        # Corrupt the state file with garbage bytes
        if os.path.exists(state_file):
            atf.run_command(
                f"dd if=/dev/urandom of={state_file} bs=128 count=1 conv=notrunc",
                user=_slurm_user(),
                fatal=False,
            )

        try:
            # Use -i to bypass fatal on corrupt state (Slurm native behavior)
            _start_slurmctld(ignore_state_errors=True)
            ping = atf.run_command("scontrol ping", quiet=True)
            assert "is UP" in ping.get("stdout", ""), (
                "slurmctld must start with -i despite corrupt app_state"
            )
        finally:
            _delete_app("corrupt_pre")

    def test_missing_state_file_handled(self):
        """
        Delete spool/app_state. slurmctld must start successfully and use
        config-defined apps only.

        Source: _open_app_state_file() returns NULL → load_all_app_state()
                logs "No app state file ... to recover" and returns 0.
        """
        state_file = _get_app_state_file()
        if not state_file:
            pytest.skip("Cannot determine StateSaveLocation")

        # Add a config app so there is something to load after delete
        conf_app = "missapp_conf"
        _add_app_to_conf(conf_app, version="1.0")

        try:
            _stop_slurmctld()
            atf.run_command(
                f"rm -f {state_file} {state_file}.old {state_file}.new",
                user=_slurm_user(),
                fatal=False,
            )
            _start_slurmctld()

            ping = atf.run_command("scontrol ping", quiet=True)
            assert "is UP" in ping.get("stdout", ""), (
                "slurmctld must start with no app_state file"
            )
            show = _show_app(conf_app)
            assert f"AppName={conf_app}" in show["stdout"], (
                "Config-defined app should still be loaded"
            )
        finally:
            _remove_app_from_conf(conf_app)
            _reconfigure()

    def test_old_version_state_file(self):
        """
        Replace state file header with an unknown version string.
        Loader must safely skip and not block startup.

        Source: load_all_app_state() L1880-1885 — when version string does
                not match APP_STATE_VERSION, protocol_version stays NO_VAL16
                and unpack proceeds with safe defaults / unpack_error path.
        """
        state_file = _get_app_state_file()
        if not state_file:
            pytest.skip("Cannot determine StateSaveLocation")

        self._ensure_keep_app_info()

        # Generate a real state file by creating an app
        _create_app("oldver_pre", version="1.0")
        time.sleep(2)

        _stop_slurmctld()

        # Overwrite first bytes with an obviously wrong version marker.
        # Use printf to avoid trailing newline; truncate to keep size sane.
        if os.path.exists(state_file):
            atf.run_command(
                f"printf 'BOGUS_OLD_VERSION_999' > {state_file}",
                user=_slurm_user(),
                fatal=False,
            )

        try:
            # Use -i to bypass fatal on version mismatch (Slurm native behavior)
            _start_slurmctld(ignore_state_errors=True)
            ping = atf.run_command("scontrol ping", quiet=True)
            assert "is UP" in ping.get("stdout", ""), (
                "slurmctld must start with -i on unknown state file version"
            )
        finally:
            _delete_app("oldver_pre")
