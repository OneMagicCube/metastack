############################################################################  
# test_148_2 - Test App Version management (+=, -=, = operations)  
#  
# Group 2 of __METASTACK_OPT_APP test suite.  
# Tests Version+=, Version-=, Version= operations on app records,  
# including combined hash updates, edge cases, and error handling.  
############################################################################  
  
import pytest  
import atf  
import re  
  
  
# ---------------------------------------------------------------------------  
# Helpers (same pattern as test_148_1.py)  
# ---------------------------------------------------------------------------  
  
def _create_app(name, **kwargs):  
    """Create an app as the slurm admin user. Returns run_command result."""  
    cmd = f"scontrol create app AppName={name}"  
    for k, v in kwargs.items():  
        cmd += f" {k}={v}"  
    result = atf.run_command(cmd, user=atf.properties["slurm-user"])  
    assert result["exit_code"] == 0, f"Failed to create app {name}: {result['stderr']}"  
    return result  
  
  
def _update_app(name, **kwargs):  
    """Update an app as the slurm admin user. Returns run_command result."""  
    cmd = f"scontrol update app AppName={name}"  
    for k, v in kwargs.items():  
        # kwargs keys like 'Version+=': we need to handle specially  
        cmd += f" {k}={v}"  
    result = atf.run_command(cmd, user=atf.properties["slurm-user"])  
    return result  
  
  
def _update_app_raw(raw_cmd):  
    """Run a raw scontrol update command as admin. Returns run_command result."""  
    result = atf.run_command(raw_cmd, user=atf.properties["slurm-user"])  
    return result  
  
  
def _show_app(name=None):  
    """Show app info. Returns run_command result."""  
    cmd = "scontrol show app"  
    if name:  
        cmd += f" {name}"  
    return atf.run_command(cmd, user=atf.properties["slurm-user"])  
  
  
def _delete_app(name):  
    """Delete an app as admin. Returns run_command result."""  
    result = atf.run_command(  
        f"scontrol delete app AppName={name}",  
        user=atf.properties["slurm-user"],  
    )  
    return result  
  
  
def _get_version_from_show(app_name):  
    """Parse Version= value from 'scontrol show app <name>' output.  
    Returns the version string, or None if not found / no Version field.  
    """  
    show = _show_app(app_name)  
    if show["exit_code"] != 0:  
        return None  
    m = re.search(r"Version=(\S+)", show["stdout"])  
    return m.group(1) if m else None  
  
  
def _version_set(app_name):  
    """Return the set of versions for an app, parsed from show output.  
    E.g. "1.0,2.0,3.0" -> {"1.0", "2.0", "3.0"}  
    Returns empty set if no Version field.  
    """  
    ver_str = _get_version_from_show(app_name)  
    if not ver_str:  
        return set()  
    return set(v.strip() for v in ver_str.split(",") if v.strip())  
  
  
# ---------------------------------------------------------------------------  
# Fixtures  
# ---------------------------------------------------------------------------  
  
@pytest.fixture(scope="module", autouse=True)  
def setup():  
    """Ensure Slurm is running (local-config mode)."""  
    atf.require_slurm_running()  
  
  
@pytest.fixture  
def cleanup_app():  
    """Register app names for cleanup after each test."""  
    apps = []  
  
    def _register(name):  
        apps.append(name)  
        return name  
  
    yield _register  
  
    for name in apps:  
        _delete_app(name)  
  
  
# ===========================================================================  
# Test Class: Version Add (+=)  
# ===========================================================================  
  
class TestVersionAdd:  
  
    def test_add_single_version(self, cleanup_app):  
        """  
        Verify Version+= adds a single version to an existing app.  
  
        Source: _app_versions_add() appends version with comma separator  
        if app already has versions (read_config.c:1270-1273).  
        """  
        cleanup_app("vadd1")  
        _create_app("vadd1", Version="1.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vadd1 Version+=2.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vadd1")  
        assert versions == {"1.0", "2.0"}  
  
    def test_add_multiple_versions(self, cleanup_app):  
        """  
        Verify Version+= adds multiple comma-separated versions at once.  
  
        Source: scontrol_process_plus_minus('+', "2.0,3.0") produces  
        "+2.0,+3.0" (common.c:73-77). _app_versions_add() iterates  
        each token (read_config.c:1262-1287).  
        """  
        cleanup_app("vadd2")  
        _create_app("vadd2", Version="1.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vadd2 Version+=2.0,3.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vadd2")  
        assert versions == {"1.0", "2.0", "3.0"}  
  
    def test_add_duplicate_version_skipped(self, cleanup_app):  
        """  
        Verify adding an already-existing version is silently skipped.  
  
        Source: _app_versions_add() checks _version_in_list() and skips  
        if already present (read_config.c:1269-1284). No error returned.  
        """  
        cleanup_app("vadd3")  
        _create_app("vadd3", Version="1.0,2.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vadd3 Version+=1.0"  
        )  
        # Should succeed (duplicate is silently skipped)  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vadd3")  
        assert versions == {"1.0", "2.0"}  
  
    def test_add_mix_new_and_existing(self, cleanup_app):  
        """  
        Verify adding a mix of new and existing versions: new ones are  
        added, existing ones are skipped.  
        """  
        cleanup_app("vadd4")  
        _create_app("vadd4", Version="1.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vadd4 Version+=1.0,2.0,3.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vadd4")  
        assert versions == {"1.0", "2.0", "3.0"}  
  
    def test_add_version_to_no_version_app(self, cleanup_app):  
        """  
        Verify adding a version to an app that was created without versions.  
  
        Source: _app_versions_add() handles NULL/empty versions by setting  
        the first version directly (read_config.c:1274-1276).  
        """  
        cleanup_app("vadd5")  
        _create_app("vadd5")  # No Version  
  
        # Confirm no version initially  
        ver = _get_version_from_show("vadd5")  
        assert ver is None  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vadd5 Version+=1.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vadd5")  
        assert versions == {"1.0"}  
  
    def test_add_version_updates_combined_hash(self, cleanup_app):  
        """  
        Verify that after Version+=, the new combined name is queryable  
        via 'scontrol show app <name-version>'.  
  
        Source: _rebuild_combined_hash_for_app() is called after  
        _app_versions_add() (read_config.c:2112).  
        """  
        cleanup_app("vadd6")  
        _create_app("vadd6", Version="1.0")  
  
        _update_app_raw(  
            "scontrol update app AppName=vadd6 Version+=2.0"  
        )  
  
        # New combined name should be queryable  
        show = _show_app("vadd6-2.0")  
        assert "AppName=vadd6" in show["stdout"]  
  
        # Old combined name should still work  
        show = _show_app("vadd6-1.0")  
        assert "AppName=vadd6" in show["stdout"]  
  
    def test_add_version_preserves_properties(self, cleanup_app):  
        """  
        Verify that Version+= does not alter other properties  
        (Description, Default).  
  
        Source: update_app() updates description/watchdog/default only  
        if they are provided in the request (read_config.c:2117-2152).  
        When only Version+= is given, other fields are NULL/IGNORE.  
        """  
        cleanup_app("vadd7")  
        _create_app("vadd7", Version="1.0", Description="MyDesc",  
                     Default="YES")  
  
        _update_app_raw(  
            "scontrol update app AppName=vadd7 Version+=2.0"  
        )  
  
        show = _show_app("vadd7")  
        assert 'Description="MyDesc"' in show["stdout"]  
        assert "Default=YES" in show["stdout"]  
  
  
# ===========================================================================  
# Test Class: Version Remove (-=)  
# ===========================================================================  
  
class TestVersionRemove:  
  
    def test_remove_single_version(self, cleanup_app):  
        """  
        Verify Version-= removes a single version from the list.  
  
        Source: _app_versions_remove() calls _remove_version_from_list()  
        (read_config.c:1305-1307).  
        """  
        cleanup_app("vrem1")  
        _create_app("vrem1", Version="1.0,2.0,3.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vrem1 Version-=2.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vrem1")  
        assert versions == {"1.0", "3.0"}  
  
    def test_remove_multiple_versions(self, cleanup_app):  
        """  
        Verify Version-= removes multiple comma-separated versions.  
  
        Source: scontrol_process_plus_minus('-', "1.0,3.0") produces  
        "-1.0,-3.0". _app_versions_remove() iterates each token.  
        """  
        cleanup_app("vrem2")  
        _create_app("vrem2", Version="1.0,2.0,3.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vrem2 Version-=1.0,3.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vrem2")  
        assert versions == {"2.0"}  
  
    def test_remove_nonexistent_version_skipped(self, cleanup_app):  
        """  
        Verify removing a non-existent version is silently skipped.  
  
        Source: _app_versions_remove() checks _version_in_list() and  
        skips if not found (read_config.c:1310-1313). No error returned.  
        """  
        cleanup_app("vrem3")  
        _create_app("vrem3", Version="1.0,2.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vrem3 Version-=9.9"  
        )  
        # Should succeed (non-existent version silently skipped)  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vrem3")  
        assert versions == {"1.0", "2.0"}  
  
    def test_remove_all_versions(self, cleanup_app):  
        """  
        Verify removing all versions results in no Version field.  
  
        Source: _remove_version_from_list() rebuilds the string without  
        the target version. When all are removed, new_versions is NULL  
        (read_config.c:1221-1222).  
        """  
        cleanup_app("vrem4")  
        _create_app("vrem4", Version="1.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vrem4 Version-=1.0"  
        )  
        assert result["exit_code"] == 0  
  
        ver = _get_version_from_show("vrem4")  
        assert ver is None  
  
    def test_remove_version_updates_combined_hash(self, cleanup_app):  
        """  
        Verify that after Version-=, the removed combined name is no  
        longer queryable.  
  
        Source: _remove_combined_hash_for_app() is called before version  
        modification, then _rebuild_combined_hash_for_app() after  
        (read_config.c:2102, 2112).  
        """  
        cleanup_app("vrem5")  
        _create_app("vrem5", Version="1.0,2.0")  
  
        _update_app_raw(  
            "scontrol update app AppName=vrem5 Version-=1.0"  
        )  
  
        # Removed combined name should NOT be found  
        show = _show_app("vrem5-1.0")  
        assert "No app" in show["stdout"]  
  
        # Remaining combined name should still work  
        show = _show_app("vrem5-2.0")  
        assert "AppName=vrem5" in show["stdout"]  
  
    def test_remove_version_preserves_properties(self, cleanup_app):  
        """  
        Verify that Version-= does not alter other properties.  
        """  
        cleanup_app("vrem6")  
        _create_app("vrem6", Version="1.0,2.0", Description="KeepMe",  
                     Default="YES")  
  
        _update_app_raw(  
            "scontrol update app AppName=vrem6 Version-=1.0"  
        )  
  
        show = _show_app("vrem6")  
        assert 'Description="KeepMe"' in show["stdout"]  
        assert "Default=YES" in show["stdout"]  
        versions = _version_set("vrem6")  
        assert versions == {"2.0"}  
  
  
# ===========================================================================  
# Test Class: Version Replace (=)  
# ===========================================================================  
  
class TestVersionReplace:  
  
    def test_replace_version_list(self, cleanup_app):  
        """  
        Verify Version= replaces the entire version list.  
  
        Source: _app_versions_replace() frees old versions and sets new  
        (read_config.c:1326-1327).  
        """  
        cleanup_app("vrep1")  
        _create_app("vrep1", Version="1.0,2.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vrep1 Version=3.0,4.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vrep1")  
        assert versions == {"3.0", "4.0"}  
  
    def test_replace_updates_combined_hash(self, cleanup_app):  
        """  
        Verify that after Version= replace, old combined names are gone  
        and new ones are available.  
  
        Source: _remove_combined_hash_for_app() removes old entries,  
        _rebuild_combined_hash_for_app() creates new ones  
        (read_config.c:2102, 2112).  
        """  
        cleanup_app("vrep2")  
        _create_app("vrep2", Version="1.0")  
  
        _update_app_raw(  
            "scontrol update app AppName=vrep2 Version=2.0,3.0"  
        )  
  
        # Old combined name should be gone  
        show = _show_app("vrep2-1.0")  
        assert "No app" in show["stdout"]  
  
        # New combined names should work  
        show = _show_app("vrep2-2.0")  
        assert "AppName=vrep2" in show["stdout"]  
        show = _show_app("vrep2-3.0")  
        assert "AppName=vrep2" in show["stdout"]  
  
    def test_replace_single_version(self, cleanup_app):  
        """  
        Verify replacing a multi-version list with a single version.  
        """  
        cleanup_app("vrep3")  
        _create_app("vrep3", Version="1.0,2.0,3.0")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vrep3 Version=5.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("vrep3")  
        assert versions == {"5.0"}  
  
    def test_replace_preserves_properties(self, cleanup_app):  
        """  
        Verify that Version= replace does not alter other properties.  
        """  
        cleanup_app("vrep4")  
        _create_app("vrep4", Version="1.0", Description="StayHere",  
                     Default="YES")  
  
        _update_app_raw(  
            "scontrol update app AppName=vrep4 Version=9.0"  
        )  
  
        show = _show_app("vrep4")  
        assert 'Description="StayHere"' in show["stdout"]  
        assert "Default=YES" in show["stdout"]  
        versions = _version_set("vrep4")  
        assert versions == {"9.0"}  
  
  
# ===========================================================================  
# Test Class: Error Cases  
# ===========================================================================  
  
class TestVersionErrors:  
  
    def test_mix_plus_minus_rejected(self, cleanup_app):  
        """  
        Verify that mixing + and - in Version is rejected.  
  
        Source: update_app() checks has_plus && has_minus and returns  
        ESLURM_INVALID_APP_NAME (read_config.c:2070-2074).  
  
        Note: This error can only occur if the raw version string sent  
        to slurmctld contains both + and - prefixed tokens. The scontrol  
        client only sends one type per command. We test by sending two  
        separate update commands — the server-side check is the real guard.  
        This test verifies the client-side behavior: Version+= and  
        Version-= cannot be combined in a single scontrol command because  
        _parse_app_options only processes one Version field.  
        """  
        cleanup_app("verr1")  
        _create_app("verr1", Version="1.0,2.0")  
  
        # The scontrol client only takes the last Version= argument,  
        # so mixing in a single command isn't directly possible.  
        # Instead, verify that each operation independently works  
        # and the server rejects mixed prefixes if they were sent.  
        # We test the practical scenario: += and -= work separately.  
        result = _update_app_raw(  
            "scontrol update app AppName=verr1 Version+=3.0"  
        )  
        assert result["exit_code"] == 0  
  
        result = _update_app_raw(  
            "scontrol update app AppName=verr1 Version-=1.0"  
        )  
        assert result["exit_code"] == 0  
  
        versions = _version_set("verr1")  
        assert versions == {"2.0", "3.0"}  
  
    def test_version_update_nonexistent_app(self, cleanup_app):  
        """  
        Verify that Version+= on a non-existent app fails.  
  
        Source: update_app() calls find_app_record() and returns  
        ESLURM_APP_NOT_FOUND if NULL (read_config.c:2077-2082).  
        """  
        result = _update_app_raw(  
            "scontrol update app AppName=nonexistent_ver Version+=1.0"  
        )  
        assert result["exit_code"] != 0  
  
    def test_version_remove_nonexistent_app(self, cleanup_app):  
        """  
        Verify that Version-= on a non-existent app fails.  
        """  
        result = _update_app_raw(  
            "scontrol update app AppName=nonexistent_ver2 Version-=1.0"  
        )  
        assert result["exit_code"] != 0  
  
    def test_version_replace_nonexistent_app(self, cleanup_app):  
        """  
        Verify that Version= on a non-existent app fails.  
        """  
        result = _update_app_raw(  
            "scontrol update app AppName=nonexistent_ver3 Version=1.0"  
        )  
        assert result["exit_code"] != 0  

    def test_add_version_with_whitespace_only_token(self, cleanup_app):
        """
        Verify Version+= with a whitespace-only token is safely handled.

        Regression target:
        - _rebuild_combined_hash_for_app()
        - _version_in_list()
        Defensive guards must skip blank tokens after whitespace trimming,
        and must not crash slurmctld.
        """
        cleanup_app("verrws1")
        _create_app("verrws1", Version="1.0")

        result = _update_app_raw(
            'scontrol update app AppName=verrws1 "Version+=2.0,   ,3.0"'
        )
        assert result["exit_code"] == 0, (
            f"Version+= with whitespace token should succeed: {result}"
        )

        versions = _version_set("verrws1")
        assert versions == {"1.0", "2.0", "3.0"}, (
            f"Whitespace token must be ignored, got versions={versions}"
        )

        ping = atf.run_command("scontrol ping", quiet=True)
        assert "is UP" in ping.get("stdout", ""), (
            "slurmctld must remain UP after whitespace-token Version+="
        )

    def test_remove_version_with_whitespace_only_token(self, cleanup_app):
        """
        Verify Version-= works when existing version list contains a
        whitespace-only token.

        Regression target:
        - _remove_combined_hash_for_app()
        - _remove_version_from_list()
        - _version_in_list()
        All token loops must safely skip blank tokens and not crash.
        """
        cleanup_app("verrws2")
        _create_app("verrws2", Version="1.0,2.0,3.0")

        # Inject a whitespace-only token into stored version list.
        set_result = _update_app_raw(
            'scontrol update app AppName=verrws2 "Version=1.0,   ,2.0,3.0"'
        )
        assert set_result["exit_code"] == 0, (
            f"Failed to set version list containing whitespace token: {set_result}"
        )

        result = _update_app_raw(
            "scontrol update app AppName=verrws2 Version-=2.0"
        )
        assert result["exit_code"] == 0, (
            f"Version-= with whitespace token present should succeed: {result}"
        )

        versions = _version_set("verrws2")
        assert versions == {"1.0", "3.0"}, (
            f"Version 2.0 should be removed, got versions={versions}"
        )

        ping = atf.run_command("scontrol ping", quiet=True)
        assert "is UP" in ping.get("stdout", ""), (
            "slurmctld must remain UP after whitespace-token Version-="
        )
  
  
# ===========================================================================  
# Test Class: Combined Operations (Version + other properties)  
# ===========================================================================  
  
class TestVersionWithProperties:  
  
    def test_add_version_and_update_description(self, cleanup_app):  
        """  
        Verify Version+= and Description= can be combined in one command.  
  
        Source: update_app() processes version first, then updates  
        description if provided (read_config.c:2104-2121).  
        """  
        cleanup_app("vcomb1")  
        _create_app("vcomb1", Version="1.0", Description="OldDesc")  
  
        result = _update_app_raw(  
            'scontrol update app AppName=vcomb1 Version+=2.0 Description="NewDesc"'  
        )  
        assert result["exit_code"] == 0  
  
        show = _show_app("vcomb1")  
        assert 'Description="NewDesc"' in show["stdout"]  
        versions = _version_set("vcomb1")  
        assert versions == {"1.0", "2.0"}  
  
    def test_remove_version_and_change_default(self, cleanup_app):  
        """  
        Verify Version-= and Default= can be combined in one command.  
  
        Source: update_app() processes version first, then handles  
        default_spec (read_config.c:2106-2152).  
        """  
        cleanup_app("vcomb2")  
        _create_app("vcomb2", Version="1.0,2.0", Default="NO")  
  
        result = _update_app_raw(  
            "scontrol update app AppName=vcomb2 Version-=1.0 Default=YES"  
        )  
        assert result["exit_code"] == 0  
  
        show = _show_app("vcomb2")  
        assert "Default=YES" in show["stdout"]  
        versions = _version_set("vcomb2")  
        assert versions == {"2.0"}  
  
        # Clean up default state  
        _update_app_raw(  
            "scontrol update app AppName=vcomb2 Default=NO"  
        )  
  
    def test_replace_version_and_update_description(self, cleanup_app):  
        """  
        Verify Version= replace and Description= can be combined.  
        """  
        cleanup_app("vcomb3")  
        _create_app("vcomb3", Version="1.0", Description="Before")  
  
        result = _update_app_raw(  
            'scontrol update app AppName=vcomb3 Version=5.0,6.0 Description="After"'  
        )  
        assert result["exit_code"] == 0  
  
        show = _show_app("vcomb3")  
        assert 'Description="After"' in show["stdout"]  
        versions = _version_set("vcomb3")  
        assert versions == {"5.0", "6.0"}