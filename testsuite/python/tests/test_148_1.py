############################################################################  
# test_108_app_crud.py - Test scontrol create/show/update/delete app  
#  
# Tests the basic CRUD operations for the App subsystem  
# (__METASTACK_OPT_APP).  
#  
# All verification points are derived from the source code:  
#   - scontrol_create_app()   src/scontrol/scontrol.c:951-985  
#   - _print_config_app()     src/scontrol/scontrol.c:797-876  
#   - scontrol_update_app()   src/scontrol/scontrol.c:991-1024  
#   - _delete_it() app branch src/scontrol/scontrol.c:2328-2340  
#   - update_app()            src/slurmctld/read_config.c:2004-2217  
#   - delete_app()            src/slurmctld/read_config.c:2230-2263  
#   - slurm_sprint_app_info() src/api/config_info.c:2415-2446  
#   - _slurm_rpc_create_app() src/slurmctld/proc_req.c:2412-2426  
############################################################################  
import atf  
import pytest  
import re  
  
  
# ---------------------------------------------------------------------------  
# Fixtures  
# ---------------------------------------------------------------------------  
@pytest.fixture(scope="module", autouse=True)  
def setup():  
    """Ensure Slurm is running (local-config mode: skip if not running)."""  
    atf.require_slurm_running()
  
  
@pytest.fixture  
def cleanup_app():  
    """  
    Fixture that collects app names created during a test and deletes them  
    in teardown.  Usage:  
  
        def test_xxx(cleanup_app):  
            cleanup_app("myapp")  
            atf.run_command("scontrol create app AppName=myapp", ...)  
    """  
    created = []  
  
    def _register(name):  
        created.append(name)  
  
    yield _register  
  
    for name in created:  
        atf.run_command(  
            f"scontrol delete app={name}",  
            user=atf.properties["slurm-user"],  
            quiet=True,  
        )  
  
  
# ---------------------------------------------------------------------------  
# Helper  
# ---------------------------------------------------------------------------  
def _create_app(name, **kwargs):  
    """  
    Helper: run 'scontrol create app AppName=<name> [key=val ...]'  
    as the slurm admin user.  Returns the run_command result dict.  
    """  
    parts = [f"scontrol create app AppName={name}"]  
    for k, v in kwargs.items():  
        parts.append(f"{k}={v}")  
    cmd = " ".join(parts)  
    return atf.run_command(cmd, user=atf.properties["slurm-user"])  
  
  
def _show_app(name=None):  
    """  
    Helper: run 'scontrol show app [name]'.  
    Returns the run_command result dict.  
    """  
    cmd = "scontrol show app"  
    if name:  
        cmd += f" {name}"  
    return atf.run_command(cmd, quiet=True)  
  
  
def _delete_app(name):  
    """  
    Helper: run 'scontrol delete app=<name>' as admin.  
    Returns the run_command result dict.  
    """  
    return atf.run_command(  
        f"scontrol delete app={name}",  
        user=atf.properties["slurm-user"],  
    )  
  
  
# ===================================================================  
# CREATE tests  
# ===================================================================  
class TestCreateApp:  
    """Tests for 'scontrol create app'."""  
  
    def test_create_app_basic(self, cleanup_app):  
        """  
        Verify that creating an app with AppName and Version succeeds.  
  
        Source: scontrol_create_app() prints "App created: <name>\\n"  
        on success (scontrol.c:977).  
        """  
        cleanup_app("testapp1")  
        result = _create_app("testapp1", Version="1.0,2.0")  
        assert result["exit_code"] == 0  
        assert "App created: testapp1" in result["stdout"]  
  
    def test_create_app_no_version(self, cleanup_app):  
        """  
        Verify that creating an app WITHOUT Version succeeds.  
        Version is optional — omitting it means no version restriction.  
  
        Source: scontrol_create_app() comment at scontrol.c:968.  
        """  
        cleanup_app("noversionapp")  
        result = _create_app("noversionapp")  
        assert result["exit_code"] == 0  
        assert "App created: noversionapp" in result["stdout"]  
  
    def test_create_app_with_description(self, cleanup_app):  
        """  
        Verify that Description field is accepted and stored.  
  
        Source: _parse_app_options() handles "Description" (scontrol.c:924-927).  
        slurm_sprint_app_info() outputs Description="..." (config_info.c:2428-2429).  
        """  
        cleanup_app("descapp")  
        result = _create_app("descapp", Version="1.0", Description='"Test App"')  
        assert result["exit_code"] == 0  
  
        show = _show_app("descapp")  
        assert 'Description="Test App"' in show["stdout"]  
  
    def test_create_app_with_default_yes(self, cleanup_app):  
        """  
        Verify that Default=YES is accepted and shown.  
  
        Source: _parse_app_options() sets APP_DESC_DEFAULT_YES (scontrol.c:932-936).  
        slurm_sprint_app_info() outputs " Default=YES" (config_info.c:2435-2436).  
        """  
        cleanup_app("defaultapp")  
        result = _create_app("defaultapp", Version="1.0", Default="YES")  
        assert result["exit_code"] == 0  
  
        show = _show_app("defaultapp")  
        assert "Default=YES" in show["stdout"]  
  
    def test_create_app_default_is_no_by_default(self, cleanup_app):  
        """  
        Verify that when Default is not specified, it defaults to NO.  
  
        Source: slurm_init_app_desc_msg() sets default_spec=APP_DESC_DEFAULT_IGNORE  
        (slurm_protocol_defs.c:4320-4321), and _parse_app_name() sets  
        default_flag=false if not specified (read_config.c:2095).  
        slurm_sprint_app_info() outputs " Default=NO" (config_info.c:2437-2438).  
        """  
        cleanup_app("nodefaultapp")  
        result = _create_app("nodefaultapp", Version="1.0")  
        assert result["exit_code"] == 0  
  
        show = _show_app("nodefaultapp")  
        assert "Default=NO" in show["stdout"]  
  
    def test_create_duplicate_app(self, cleanup_app):  
        """  
        Verify that creating an app with a duplicate AppName fails.  
  
        Source: update_app() with create_flag=true checks find_app_record()  
        and returns ESLURM_APP_ALREADY_EXISTS (read_config.c:2030-2033).  
        scontrol_create_app() calls slurm_perror("Error creating the app")  
        (scontrol.c:972).  
        """  
        cleanup_app("dupapp")  
        _create_app("dupapp", Version="1.0")  
  
        result = _create_app("dupapp", Version="2.0")  
        assert result["exit_code"] != 0  
        assert "Error creating the app" in result["stderr"]  
  
    def test_create_app_missing_name(self):  
        """  
        Verify that creating an app without AppName fails.  
  
        Source: scontrol_create_app() checks !app_msg.app_name and  
        calls error("AppName must be given.") (scontrol.c:963-966).  
        """  
        result = atf.run_command(  
            "scontrol create app Version=1.0",  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] != 0  
        assert "AppName must be given" in result["stderr"]  
  
    def test_create_app_no_params(self):  
        """  
        Verify that 'scontrol create app' with no parameters fails.  
  
        Source: scontrol_create_app() checks _parse_app_options()==0 and  
        calls error("No parameters specified") (scontrol.c:957-960).  
        """  
        result = atf.run_command(  
            "scontrol create app",  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] != 0  
  
    def test_create_app_requires_admin(self, cleanup_app):  
        """  
        Verify that a non-admin user cannot create an app.  
  
        Source: _slurm_rpc_create_app() calls validate_super_user() and  
        returns ESLURM_USER_ID_MISSING on failure (proc_req.c:2422-2425).  
        """  
        cleanup_app("admintest")  
        result = atf.run_command(  
            "scontrol create app AppName=admintest Version=1.0",  
        )  
        # run_command without user= runs as the test user (non-admin)  
        assert result["exit_code"] != 0  
  
  
# ===================================================================  
# SHOW tests  
# ===================================================================  
class TestShowApp:  
    """Tests for 'scontrol show app'."""  
  
    def test_show_app_by_name(self, cleanup_app):  
        """  
        Verify that 'scontrol show app <name>' displays the correct app.  
  
        Source: _print_config_app() matches config_param against  
        app_ptr[i].app_name (scontrol.c:835-837).  
        slurm_sprint_app_info() outputs "AppName=<name>" (config_info.c:2423).  
        """  
        cleanup_app("showapp1")  
        _create_app("showapp1", Version="3.0,4.0")  
  
        show = _show_app("showapp1")  
        assert show["exit_code"] == 0  
        assert "AppName=showapp1" in show["stdout"]  
        assert "Version=3.0,4.0" in show["stdout"]  
  
    def test_show_app_by_combined_name(self, cleanup_app):  
        """  
        Verify that 'scontrol show app <name>-<version>' matches via  
        the combined name format.  
  
        Source: _print_config_app() tokenizes versions and checks each  
        "appname-version" combination (scontrol.c:838-857).  
        """  
        cleanup_app("combapp")  
        _create_app("combapp", Version="5.0,6.0")  
  
        show = _show_app("combapp-5.0")  
        assert show["exit_code"] == 0  
        assert "AppName=combapp" in show["stdout"]  
  
    def test_show_app_not_found(self, cleanup_app):  
        """  
        Verify that showing a non-existent app prints the expected message.  
  
        Source: _print_config_app() prints "No app '<name>' found.\\n"  
        when print_cnt==0 and config_param is set (scontrol.c:871-872).  
        """  
        show = _show_app("nonexistent_app_xyz")  
        assert "No app 'nonexistent_app_xyz' found." in show["stdout"]  
  
    def test_show_app_all(self, cleanup_app):  
        """  
        Verify that 'scontrol show app' (no argument) lists all apps.  
  
        Source: _print_config_app() iterates all records when  
        config_param is NULL (scontrol.c:832-863).  
        """  
        cleanup_app("allapp1")  
        cleanup_app("allapp2")  
        _create_app("allapp1", Version="1.0")  
        _create_app("allapp2", Version="2.0")  
  
        show = _show_app()  
        assert "AppName=allapp1" in show["stdout"]  
        assert "AppName=allapp2" in show["stdout"]  
  
    def test_show_no_apps_configured(self):  
        """  
        Verify that when no apps exist, the output says so.  
  
        Source: _print_config_app() prints "No apps configured.\\n"  
        when print_cnt==0 and config_param is NULL (scontrol.c:873-874).  
  
        NOTE: This test may be fragile if other tests leave apps behind  
        or if slurm.conf defines AppName lines. It is best run in a  
        clean auto-config environment with no AppName in slurm.conf.  
        """  
        # First, get current apps and delete them all  
        show = _show_app()  
        if "No apps configured" in show["stdout"]:  
            # Already clean  
            return  
  
        # Extract all app names and delete them  
        app_names = re.findall(r"AppName=(\S+)", show["stdout"])  
        for name in app_names:  
            _delete_app(name)  
  
        show = _show_app()  
        assert "No apps configured." in show["stdout"]  
  
    def test_show_app_output_format(self, cleanup_app):  
        """  
        Verify the exact output format of 'scontrol show app'.  
  
        Source: slurm_sprint_app_info() (config_info.c:2415-2446):  
          Line 1: "AppName=<name> Version=<ver>"  (Version only if non-empty)  
          Line 2: "   Description=\"<desc>\" Watchdog=<wd> Default=YES|NO"  
                   (Description/Watchdog only if non-empty)  
        """  
        cleanup_app("fmtapp")  
        _create_app("fmtapp", Version="1.0", Description='"My App"', Default="YES")  
  
        show = _show_app("fmtapp")  
        stdout = show["stdout"]  
  
        assert "AppName=fmtapp" in stdout  
        assert "Version=1.0" in stdout  
        assert 'Description="My App"' in stdout  
        assert "Default=YES" in stdout  
  
    def test_show_app_no_version_field(self, cleanup_app):  
        """  
        Verify that an app created without Version does not show  
        'Version=' in the output.  
  
        Source: slurm_sprint_app_info() only appends " Version=..."  
        if app_ptr->versions is non-NULL and non-empty (config_info.c:2424-2425).  
        """  
        cleanup_app("noverapp")  
        _create_app("noverapp")  
  
        show = _show_app("noverapp")  
        assert "AppName=noverapp" in show["stdout"]  
        assert "Version=" not in show["stdout"]  
  
  
# ===================================================================  
# UPDATE tests (properties only, Version +=/-= is in Group 2)  
# ===================================================================  
class TestUpdateApp:  
    """Tests for 'scontrol update app' — property updates only."""  
  
    def test_update_description(self, cleanup_app):  
        """  
        Verify that updating Description changes the stored value.  
  
        Source: update_app() no-version branch sets  
        app_ptr->description = xstrdup(app_desc->description)  
        (read_config.c:2179-2182).  
        """  
        cleanup_app("updapp1")  
        _create_app("updapp1", Version="1.0", Description='"Old Desc"')  
  
        result = atf.run_command(  
            'scontrol update app AppName=updapp1 Description="New Desc"',  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] == 0  
  
        show = _show_app("updapp1")  
        assert 'Description="New Desc"' in show["stdout"]  
  
    def test_update_default_yes(self, cleanup_app):  
        """  
        Verify that setting Default=YES on an app makes it the default,  
        and clears the previous default.  
  
        Source: update_app() sets app_ptr->default_flag=true and clears  
        old default_app_loc->default_flag (read_config.c:2189-2203).  
        """  
        cleanup_app("defapp_a")  
        cleanup_app("defapp_b")  
        _create_app("defapp_a", Version="1.0", Default="YES")  
        _create_app("defapp_b", Version="1.0")  
  
        # Verify A is default  
        show_a = _show_app("defapp_a")  
        assert "Default=YES" in show_a["stdout"]  
  
        # Make B the default  
        atf.run_command(  
            "scontrol update app AppName=defapp_b Default=YES",  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
  
        # B should now be default, A should not  
        show_b = _show_app("defapp_b")  
        assert "Default=YES" in show_b["stdout"]  
  
        show_a = _show_app("defapp_a")  
        assert "Default=NO" in show_a["stdout"]  
  
    def test_update_default_no(self, cleanup_app):  
        """  
        Verify that setting Default=NO clears the default flag.  
  
        Source: update_app() sets app_ptr->default_flag=false and  
        clears default_app_name/default_app_loc (read_config.c:2204-2210).  
        """  
        cleanup_app("defnoapp")  
        _create_app("defnoapp", Version="1.0", Default="YES")  
  
        atf.run_command(  
            "scontrol update app AppName=defnoapp Default=NO",  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
  
        show = _show_app("defnoapp")  
        assert "Default=NO" in show["stdout"]  
  
    def test_update_nonexistent_app(self):  
        """  
        Verify that updating a non-existent app fails.  
  
        Source: update_app() no-version branch calls find_app_record()  
        and returns ESLURM_APP_NOT_FOUND (read_config.c:2160-2164).  
        scontrol_update_app() calls slurm_perror("Error updating the app")  
        (scontrol.c:1012).  
        """  
        result = atf.run_command(  
            'scontrol update app AppName=ghost_app Description="x"',  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] != 0  
        assert "Error updating the app" in result["stderr"]  
  
    def test_update_without_default_preserves_it(self, cleanup_app):  
        """  
        Verify that updating an app without specifying Default does not  
        change the default flag.  
  
        Source: slurm_init_app_desc_msg() sets  
        default_spec=APP_DESC_DEFAULT_IGNORE (0xff)  
        (slurm_protocol_defs.c:4320-4321).  
        update_app() skips default logic when  
        default_spec==APP_DESC_DEFAULT_IGNORE (read_config.c:2189).  
        """  
        cleanup_app("keepdefapp")  
        _create_app("keepdefapp", Version="1.0", Default="YES")  
  
        # Update description only, don't touch Default  
        atf.run_command(  
            'scontrol update app AppName=keepdefapp Description="Updated"',  
            user=atf.properties["slurm-user"],  
            fatal=True,  
        )  
  
        show = _show_app("keepdefapp")  
        assert "Default=YES" in show["stdout"]  
        assert 'Description="Updated"' in show["stdout"]  
  
  
# ===================================================================  
# DELETE tests  
# ===================================================================  
class TestDeleteApp:  
    """Tests for 'scontrol delete app'."""  
  
    def test_delete_app(self):  
        """  
        Verify that deleting an existing app succeeds and the app  
        is no longer visible.  
  
        Source: delete_app() calls find_app_record(), removes from  
        hashes and list, returns SLURM_SUCCESS (read_config.c:2230-2263).  
        """  
        _create_app("delapp1", Version="1.0")  
  
        result = _delete_app("delapp1")  
        assert result["exit_code"] == 0  
  
        show = _show_app("delapp1")  
        assert "No app 'delapp1' found." in show["stdout"]  
  
    def test_delete_app_format_equals(self):  
        """  
        Verify the 'scontrol delete app=<name>' format works.  
  
        Source: _delete_it() argc==1 branch parses tag=val from '='  
        (scontrol.c:2276-2286).  
        """  
        _create_app("deleqapp", Version="1.0")  
  
        result = atf.run_command(  
            "scontrol delete app=deleqapp",  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] == 0  
  
        show = _show_app("deleqapp")  
        assert "No app" in show["stdout"]  
  
    def test_delete_app_format_space(self):  
        """  
        Verify the 'scontrol delete app <name>' format works.  
  
        Source: _delete_it() argc==2 branch uses argv[1] as val  
        (scontrol.c:2287-2290).  
        """  
        _create_app("delspapp", Version="1.0")  
  
        result = atf.run_command(  
            "scontrol delete app delspapp",  
            user=atf.properties["slurm-user"],  
        )  
        assert result["exit_code"] == 0  
  
        show = _show_app("delspapp")  
        assert "No app" in show["stdout"]  
  
    def test_delete_app_not_found(self):  
        """  
        Verify that deleting a non-existent app fails.  
  
        Source: delete_app() calls find_app_record() and returns  
        ESLURM_APP_NOT_FOUND (read_config.c:2240-2243).  
        _delete_it() calls slurm_perror("delete_app <name>")  
        (scontrol.c:2334-2337).  
        """  
        result = _delete_app("nonexistent_del_app")  
        assert result["exit_code"] != 0  
        assert "delete_app" in result["stderr"]  
  
    def test_delete_default_app_clears_default(self, cleanup_app):  
        """  
        Verify that deleting the default app clears the default pointer.  
  
        Source: delete_app() checks app_ptr->default_flag and clears  
        default_app_name and default_app_loc (read_config.c:2246-2249).  
  
        After deletion, no app should be the default.  
        """  
        _create_app("deldefapp", Version="1.0", Default="YES")  
  
        result = _delete_app("deldefapp")  
        assert result["exit_code"] == 0  
  
        # Create a new app — it should NOT inherit default  
        cleanup_app("newapp_after_del")  
        _create_app("newapp_after_del", Version="1.0")  
        show = _show_app("newapp_after_del")  
        assert "Default=NO" in show["stdout"]  
  
    def test_delete_app_requires_admin(self):  
        """  
        Verify that a non-admin user cannot delete an app.  
  
        Source: _slurm_rpc_delete_app() calls validate_super_user()  
        (proc_req.c — same pattern as create/update).  
        """  
        _create_app("deladminapp", Version="1.0")  
  
        result = atf.run_command("scontrol delete app=deladminapp")  
        assert result["exit_code"] != 0  
  
        # Cleanup as admin  
        _delete_app("deladminapp")