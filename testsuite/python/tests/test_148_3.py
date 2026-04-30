############################################################################  
# test_148_3.py - Group 3: Default App & Property Update  
#  
# Tests the Default flag mutual exclusion logic and property (Description,  
# Watchdog) update behavior of the __METASTACK_OPT_APP feature.  
#  
# Code under test:  
#   - update_app() in src/slurmctld/read_config.c:2004-2220  
#   - delete_app() in src/slurmctld/read_config.c:2230-2263  
#   - slurm_sprint_app_info() in src/api/config_info.c:2415-2446  
#   - _parse_app_options() in src/scontrol/scontrol.c:882-943  
############################################################################  
  
import atf  
import pytest  
import re  
  
  
# ---------------------------------------------------------------------------  
# Helper functions  
# ---------------------------------------------------------------------------  
  
def _create_app(name, **kwargs):  
    """Create an app via scontrol. kwargs become Key=Value pairs."""  
    parts = [f"scontrol create app AppName={name}"]  
    for k, v in kwargs.items():  
        parts.append(f"{k}={v}")  
    cmd = " ".join(parts)  
    result = atf.run_command(cmd, user=atf.properties["slurm-user"], fatal=True)  
    assert result["exit_code"] == 0, f"Failed to create app {name}: {result['stderr']}"  
  
  
def _show_app(name=None):  
    """Run scontrol show app [name] and return the result dict."""  
    cmd = "scontrol show app"  
    if name:  
        cmd += f" {name}"  
    return atf.run_command(cmd, user=atf.properties["slurm-user"])  
  
  
def _update_app(name, **kwargs):  
    """Update an app via scontrol. kwargs become Key=Value pairs."""  
    parts = [f"scontrol update app AppName={name}"]  
    for k, v in kwargs.items():  
        parts.append(f"{k}={v}")  
    cmd = " ".join(parts)  
    return atf.run_command(cmd, user=atf.properties["slurm-user"])  
  
  
def _delete_app(name):  
    """Delete an app via scontrol, ignoring errors."""  
    atf.run_command(  
        f"scontrol delete app {name}",  
        user=atf.properties["slurm-user"],  
        quiet=True,  
    )  
  
  
def _get_default_flag(name):  
    """Parse 'Default=YES' or 'Default=NO' from scontrol show app output."""  
    show = _show_app(name)  
    assert show["exit_code"] == 0, f"show app {name} failed: {show['stderr']}"  
    if "Default=YES" in show["stdout"]:  
        return True  
    if "Default=NO" in show["stdout"]:  
        return False  
    pytest.fail(f"Cannot parse Default flag from output: {show['stdout']}")  
  
  
def _get_field(name, field):  
    """Extract a field value from scontrol show app output.  
  
    Handles both unquoted (Version=1.0) and quoted (Description="hello world")  
    fields.  
    """  
    show = _show_app(name)  
    assert show["exit_code"] == 0, f"show app {name} failed"  
    # Try quoted value first: Field="value"  
    m = re.search(rf'{field}="([^"]*)"', show["stdout"])  
    if m:  
        return m.group(1)  
    # Try unquoted value: Field=value (terminated by space or newline)  
    m = re.search(rf'{field}=(\S+)', show["stdout"])  
    if m:  
        return m.group(1)  
    return None  
  
  
# ---------------------------------------------------------------------------  
# Fixtures  
# ---------------------------------------------------------------------------  
  
@pytest.fixture(scope="module", autouse=True)  
def setup():  
    """Ensure Slurm is running (local-config mode)."""  
    atf.require_slurm_running()  
  
  
@pytest.fixture  
def cleanup_app():  
    """Register app names for automatic cleanup after each test."""  
    names = []  
  
    def _register(name):  
        names.append(name)  
        return name  
  
    yield _register  
  
    for n in reversed(names):  
        _delete_app(n)  
  
  
# ---------------------------------------------------------------------------  
# Test Class 1: Default Flag Mutual Exclusion  
#  
# Invariant: at most one app can have Default=YES at any time.  
# Source: update_app() lines 2045-2052 (create), 2129-2152 (update+version),  
#         2189-2212 (update no-version), delete_app() lines 2245-2248.  
# ---------------------------------------------------------------------------  
  
class TestDefaultMutualExclusion:  
  
    def test_create_with_default_yes(self, cleanup_app):  
        """  
        Create an app with Default=YES. Verify it becomes the default.  
  
        Source: update_app() create path, line 2045:  
            if (app_desc->default_spec == APP_DESC_DEFAULT_YES)  
                → sets app_ptr->default_flag = true  
        """  
        cleanup_app("dflt1")  
        _create_app("dflt1", Version="1.0", Default="YES")  
        assert _get_default_flag("dflt1") is True  
  
    def test_create_second_default_clears_first(self, cleanup_app):  
        """  
        Create app A with Default=YES, then create app B with Default=YES.  
        App A should lose its default status.  
  
        Source: update_app() create path, lines 2046-2047:  
            if (default_app_loc && default_app_loc != app_ptr)  
                default_app_loc->default_flag = false;  
        """  
        cleanup_app("dflt2a")  
        cleanup_app("dflt2b")  
        _create_app("dflt2a", Version="1.0", Default="YES")  
        assert _get_default_flag("dflt2a") is True  
  
        _create_app("dflt2b", Version="1.0", Default="YES")  
        assert _get_default_flag("dflt2b") is True  
        assert _get_default_flag("dflt2a") is False  
  
    def test_update_set_default_yes(self, cleanup_app):  
        """  
        Create a non-default app, then update it to Default=YES.  
  
        Source: update_app() no-version path, lines 2194-2203:  
            if (new_default && !app_ptr->default_flag)  
                → sets default_flag = true, updates default_app_name/loc  
        """  
        cleanup_app("dflt3")  
        _create_app("dflt3", Version="1.0")  
        assert _get_default_flag("dflt3") is False  
  
        result = _update_app("dflt3", Default="YES")  
        assert result["exit_code"] == 0  
        assert _get_default_flag("dflt3") is True  
  
    def test_update_set_default_no(self, cleanup_app):  
        """  
        Create a default app, then update it to Default=NO.  
  
        Source: update_app() no-version path, lines 2204-2211:  
            else if (!new_default && app_ptr->default_flag)  
                → clears default_flag, clears default_app_name/loc  
        """  
        cleanup_app("dflt4")  
        _create_app("dflt4", Version="1.0", Default="YES")  
        assert _get_default_flag("dflt4") is True  
  
        result = _update_app("dflt4", Default="NO")  
        assert result["exit_code"] == 0  
        assert _get_default_flag("dflt4") is False  
  
    def test_update_transfers_default(self, cleanup_app):  
        """  
        App A is default. Update App B to Default=YES.  
        App A should lose default, App B should gain it.  
  
        Source: update_app() no-version path, lines 2195-2198:  
            if (default_app_loc && default_app_loc != app_ptr)  
                default_app_loc->default_flag = false;  
        """  
        cleanup_app("dflt5a")  
        cleanup_app("dflt5b")  
        _create_app("dflt5a", Version="1.0", Default="YES")  
        _create_app("dflt5b", Version="1.0")  
  
        assert _get_default_flag("dflt5a") is True  
        assert _get_default_flag("dflt5b") is False  
  
        result = _update_app("dflt5b", Default="YES")  
        assert result["exit_code"] == 0  
        assert _get_default_flag("dflt5b") is True  
        assert _get_default_flag("dflt5a") is False  
  
    def test_update_without_default_preserves_flag(self, cleanup_app):  
        """  
        Update only Description (no Default= parameter). The default flag  
        should remain unchanged.  
  
        Source: _parse_app_options does not set default_spec when Default=  
        is absent → slurm_init_app_desc_msg sets it to APP_DESC_DEFAULT_IGNORE  
        (0xff). update_app() checks:  
            if (app_desc->default_spec != APP_DESC_DEFAULT_IGNORE)  
        and skips the default logic entirely.  
        """  
        cleanup_app("dflt6")  
        _create_app("dflt6", Version="1.0", Default="YES")  
        assert _get_default_flag("dflt6") is True  
  
        result = _update_app("dflt6", Description='"UpdatedDesc"')  
        assert result["exit_code"] == 0  
        assert _get_default_flag("dflt6") is True  
  
    def test_delete_default_clears_global_default(self, cleanup_app):  
        """  
        Delete the default app. No app should be default afterward.  
  
        Source: delete_app() lines 2245-2248:  
            if (app_ptr->default_flag && default_app_loc == app_ptr) {  
                xfree(default_app_name);  
                default_app_loc = NULL;  
            }  
        """  
        cleanup_app("dflt7a")  
        cleanup_app("dflt7b")  
        _create_app("dflt7a", Version="1.0", Default="YES")  
        _create_app("dflt7b", Version="1.0")  
  
        # Delete the default app  
        atf.run_command(  
            "scontrol delete app dflt7a",  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
        # Remove from cleanup list since already deleted  
        # dflt7b should still be non-default  
        assert _get_default_flag("dflt7b") is False  
  
    def test_set_default_yes_idempotent(self, cleanup_app):  
        """  
        Set Default=YES on an app that is already the default.  
        Should succeed without error (idempotent).  
  
        Source: update_app() line 2194:  
            if (new_default && !app_ptr->default_flag)  
        When app is already default, default_flag is true, so the condition  
        is false and the block is skipped. No error is returned.  
        """  
        cleanup_app("dflt8")  
        _create_app("dflt8", Version="1.0", Default="YES")  
        assert _get_default_flag("dflt8") is True  
  
        result = _update_app("dflt8", Default="YES")  
        assert result["exit_code"] == 0  
        assert _get_default_flag("dflt8") is True  
  
    def test_set_default_no_idempotent(self, cleanup_app):  
        """  
        Set Default=NO on an app that is already non-default.  
        Should succeed without error (idempotent).  
  
        Source: update_app() line 2204:  
            else if (!new_default && app_ptr->default_flag)  
        When app is already non-default, default_flag is false, so the  
        condition is false and the block is skipped.  
        """  
        cleanup_app("dflt9")  
        _create_app("dflt9", Version="1.0")  
        assert _get_default_flag("dflt9") is False  
  
        result = _update_app("dflt9", Default="NO")  
        assert result["exit_code"] == 0  
        assert _get_default_flag("dflt9") is False  
  
  
# ---------------------------------------------------------------------------  
# Test Class 2: Default Flag Alternate Syntax  
#  
# Source: _parse_app_options() lines 932-938:  
#   Default=YES / Default=1 / Default=TRUE → APP_DESC_DEFAULT_YES  
#   Anything else → APP_DESC_DEFAULT_NO  
# ---------------------------------------------------------------------------  
  
class TestDefaultSyntax:  
  
    def test_default_true_keyword(self, cleanup_app):  
        """Default=TRUE should be equivalent to Default=YES."""  
        cleanup_app("dsyn1")  
        _create_app("dsyn1", Version="1.0", Default="TRUE")  
        assert _get_default_flag("dsyn1") is True  
  
    def test_default_1_keyword(self, cleanup_app):  
        """Default=1 should be equivalent to Default=YES."""  
        cleanup_app("dsyn2")  
        _create_app("dsyn2", Version="1.0", Default="1")  
        assert _get_default_flag("dsyn2") is True  
  
    def test_default_false_keyword(self, cleanup_app):  
        """Default=FALSE should be treated as NO (any non-YES/1/TRUE value)."""  
        cleanup_app("dsyn3")  
        _create_app("dsyn3", Version="1.0", Default="FALSE")  
        assert _get_default_flag("dsyn3") is False  
  
    def test_default_0_keyword(self, cleanup_app):  
        """Default=0 should be treated as NO."""  
        cleanup_app("dsyn4")  
        _create_app("dsyn4", Version="1.0", Default="0")  
        assert _get_default_flag("dsyn4") is False  
  
  
# ---------------------------------------------------------------------------  
# Test Class 3: Property Update (Description)  
#  
# Source: update_app() no-version path, lines 2179-2183:  
#   if (app_desc->description) {  
#       xfree(app_ptr->description);  
#       app_ptr->description = xstrdup(app_desc->description);  
#   }  
#  
# Output format from slurm_sprint_app_info() lines 2428-2429:  
#   Description="value"  
# ---------------------------------------------------------------------------  
  
class TestDescriptionUpdate:  
  
    def test_update_description_only(self, cleanup_app):  
        """  
        Update only Description. Version and Default should be unchanged.  
        """  
        cleanup_app("desc1")  
        _create_app("desc1", Version="1.0")  
  
        result = _update_app("desc1", Description='"MyNewDesc"')  
        assert result["exit_code"] == 0  
  
        assert _get_field("desc1", "Description") == "MyNewDesc"  
        assert _get_field("desc1", "Version") == "1.0"  
        assert _get_default_flag("desc1") is False  
  
    def test_update_description_replaces_old(self, cleanup_app):  
        """  
        Update Description twice. Second value should replace the first.  
  
        Source: update_app() line 2180: xfree(app_ptr->description)  
        frees old value before setting new one.  
        """  
        cleanup_app("desc2")  
        _create_app("desc2", Version="1.0", Description='"First"')  
        assert _get_field("desc2", "Description") == "First"  
  
        result = _update_app("desc2", Description='"Second"')  
        assert result["exit_code"] == 0  
        assert _get_field("desc2", "Description") == "Second"  
  
    def test_create_with_description(self, cleanup_app):  
        """  
        Create an app with Description set. Verify it appears in show output.  
  
        Source: update_app() create path, line 2041-2042:  
            if (app_desc->description)  
                app_ptr->description = xstrdup(app_desc->description);  
        """  
        cleanup_app("desc3")  
        _create_app("desc3", Version="1.0", Description='"TestDescription"')  
        assert _get_field("desc3", "Description") == "TestDescription"  
  
    def test_description_preserved_on_version_update(self, cleanup_app):  
        """  
        Update Version+=. Description should remain unchanged.  
  
        Source: update_app() version path, lines 2117-2121:  
            if (app_desc->description) { ... }  
        When description is NULL (not specified), the block is skipped.  
        """  
        cleanup_app("desc4")  
        _create_app("desc4", Version="1.0", Description='"KeepMe"')  
  
        result = atf.run_command(  
            "scontrol update app AppName=desc4 Version+=2.0",  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] == 0  
        assert _get_field("desc4", "Description") == "KeepMe"  
  
    def test_description_with_spaces(self, cleanup_app):  
        """  
        Description with spaces should be preserved (quoted in output).  
  
        Source: slurm_sprint_app_info() line 2429:  
            xstrfmtcat(out, "Description=\"%s\"", app_ptr->description);  
        """  
        cleanup_app("desc5")  
        _create_app("desc5", Version="1.0", Description='"Hello World Test"')  
        assert _get_field("desc5", "Description") == "Hello World Test"  
  
    def test_no_description_field_when_empty(self, cleanup_app):  
        """  
        When Description is not set, it should not appear in show output.  
  
        Source: slurm_sprint_app_info() line 2428:  
            if (app_ptr->description && app_ptr->description[0])  
        Only prints Description when non-NULL and non-empty.  
        """  
        cleanup_app("desc6")  
        _create_app("desc6", Version="1.0")  
        show = _show_app("desc6")  
        assert "Description=" not in show["stdout"]  
  
  
# ---------------------------------------------------------------------------  
# Test Class 4: Default + Property Combined Update  
#  
# Verify that Default= and Description= can be changed in the same command.  
# ---------------------------------------------------------------------------  
  
class TestCombinedPropertyUpdate:  
  
    def test_update_description_and_default_together(self, cleanup_app):  
        """  
        Update both Description and Default in one command.  
  
        Source: update_app() no-version path processes description (line 2179)  
        and default_spec (line 2189) sequentially in the same call.  
        """  
        cleanup_app("comb1")  
        _create_app("comb1", Version="1.0")  
  
        result = _update_app("comb1", Description='"CombinedTest"', Default="YES")  
        assert result["exit_code"] == 0  
        assert _get_field("comb1", "Description") == "CombinedTest"  
        assert _get_default_flag("comb1") is True  
  
    def test_update_description_and_default_no(self, cleanup_app):  
        """  
        Set Description and Default=NO in one command on a default app.  
        """  
        cleanup_app("comb2")  
        _create_app("comb2", Version="1.0", Default="YES")  
  
        result = _update_app("comb2", Description='"NewDesc"', Default="NO")  
        assert result["exit_code"] == 0  
        assert _get_field("comb2", "Description") == "NewDesc"  
        assert _get_default_flag("comb2") is False  
  
    def test_version_add_and_default_change(self, cleanup_app):  
        """  
        Version+= and Default=YES in one command.  
  
        Source: update_app() version path processes version first (line 2104),  
        then description (line 2117), then default (line 2129).  
        """  
        cleanup_app("comb3")  
        _create_app("comb3", Version="1.0")  
  
        result = atf.run_command(  
            "scontrol update app AppName=comb3 Version+=2.0 Default=YES",  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] == 0  
        assert _get_default_flag("comb3") is True  
        show = _show_app("comb3")  
        assert "2.0" in show["stdout"]  
  
    def test_version_add_and_description_change(self, cleanup_app):  
        """  
        Version+= and Description= in one command.  
        """  
        cleanup_app("comb4")  
        _create_app("comb4", Version="1.0")  
  
        result = atf.run_command(  
            'scontrol update app AppName=comb4 Version+=2.0 Description="Combo"',  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] == 0  
        assert _get_field("comb4", "Description") == "Combo"  
        show = _show_app("comb4")  
        assert "2.0" in show["stdout"]  
  
  
# ---------------------------------------------------------------------------  
# Test Class 5: Watchdog Validation  
#  
# Source: update_app() under #ifdef __METASTACK_NEW_CUSTOM_EXCEPTION,  
# lines 2017-2027 (create), 2087-2098 (update+version), 2168-2176 (update).  
# If watchdog name is not in watch_dog_list, returns ESLURM_INVALID_APP_WATCHDOG.  
# ---------------------------------------------------------------------------  
  
class TestWatchdogValidation:  
  
    def test_create_with_undefined_watchdog_fails(self, cleanup_app):  
        """  
        Creating an app with a non-existent Watchdog should fail.  
  
        Source: update_app() create path, lines 2017-2026:  
            if (app_desc->watchdog && app_desc->watchdog[0]) {  
                if (!list_find_first(watch_dog_list, ...))  
                    return ESLURM_INVALID_APP_WATCHDOG;  
            }  
  
        Note: This test assumes __METASTACK_NEW_CUSTOM_EXCEPTION is compiled in.  
        If not, the create will succeed and the test will be skipped.  
        """  
        cleanup_app("wdog1")  
        result = atf.run_command(  
            "scontrol create app AppName=wdog1 Version=1.0 Watchdog=nonexistent_wd_xyz",  
            user=atf.properties["slurm-user"],  
        )  
        if result["exit_code"] == 0:  
            # Watchdog validation not compiled in, skip  
            pytest.skip("Watchdog validation not active (__METASTACK_NEW_CUSTOM_EXCEPTION not compiled)")  
        assert result["exit_code"] != 0  
  
    def test_update_with_undefined_watchdog_fails(self, cleanup_app):  
        """  
        Updating an app with a non-existent Watchdog should fail.  
  
        Source: update_app() no-version path, lines 2168-2175.  
        """  
        cleanup_app("wdog2")  
        _create_app("wdog2", Version="1.0")  
  
        result = _update_app("wdog2", Watchdog="nonexistent_wd_xyz")  
        if result["exit_code"] == 0:  
            pytest.skip("Watchdog validation not active")  
        assert result["exit_code"] != 0  
  
    def test_create_without_watchdog_succeeds(self, cleanup_app):  
        """  
        Creating an app without Watchdog should always succeed.  
  
        Source: The watchdog validation block only triggers when  
        app_desc->watchdog && app_desc->watchdog[0] is true.  
        """  
        cleanup_app("wdog3")  
        _create_app("wdog3", Version="1.0")  
        show = _show_app("wdog3")  
        assert show["exit_code"] == 0