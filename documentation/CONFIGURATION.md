# Configuration Reference

The launcher creates \config.json\ on first run with the following settings:

##  Region Configuration

### Per-Region Settings (replicate for each region code: de, us, fr, it, gb, pl, es, gr)

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| \current_region\ | string | \"de\" | Currently active region code |
| \show_region_<code>\ | boolean | varies | Show/hide region tab (e.g., \show_region_de\) |
| \egion_install_<code>\ | string | \"\" | Custom Wizard101 install path per region (auto-detected if empty) |
| \egion_server_<code>\ | string | varies | Login server address per region |
| \egion_port_<code>\ | integer | 12000 | Port number per region |

### Region Codes
- \de\ - Deutschland (Germany) - Default: login-de.eu.wizard101.com
- \us\ - United States - Default: uslogin.wizard101.com
- \r\ - France - Default: login-fr.eu.wizard101.com
- \it\ - Italia (Italy) - Default: login-it.eu.wizard101.com
- \gb\ - United Kingdom - Default: login-gb.eu.wizard101.com
- \pl\ - Polska (Poland) - Default: login-pl.eu.wizard101.com
- \es\ - España (Spain) - Default: login-es.eu.wizard101.com
- \gr\ - Ελλάδα (Greece) - Default: login-gr.eu.wizard101.com

---

##  Launch Configuration

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| \login_wait_seconds\ | float | 5.0 | Maximum time to wait for instance to become ready (seconds) |
| \oreground_on_login\ | boolean | true | Bring window to foreground when auto-login completes |
| \set_window_title\ | boolean | true | Update window title with account info |
| \window_title_template\ | string | \"{name} ({username})\" | Format string for window titles (use {name}, {username}) |

---

##  Playtime Tracking

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| (Auto) | - | - | Playtime data stored per account in encrypted \ccounts.enc.json\ |
| - | - | - | Fields: \	otal_playtime\, \sessions_count\, \last_session_start\ |

---

##  Logging & UI

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| \log_level\ | string | \"INFO\" | Logging verbosity: DEBUG, INFO, WARNING, ERROR |
| \ui_theme\ | string | \"WizDark\" | UI theme name (WizDark, DarkBlue, etc.) |

---

##  Advanced Settings (Rarely Changed)

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| \install_path\ | string | \"\" | **DEPRECATED** - Use region-specific \egion_install_*\ instead |
| \login_ready_timeout\ | float | 10.0 | Max wait time for instance readiness detection |
| \login_poll_interval\ | float | 0.5 | Poll interval when waiting for instance readiness |
| \ccount_sort_last_used\ | boolean | true | Sort accounts by last usage time in UI |
| \ccount_search\ | string | \"\" | Persisted account search filter text |

---

##  Example config.json

`json
{
  \"app_name\": \"Wiz Q Launcher\",
  \"app_version\": \"0.2.0\",
  \"current_region\": \"de\",
  
  \"show_region_de\": true,
  \"region_install_de\": \"\",
  \"region_server_de\": \"login-de.eu.wizard101.com\",
  \"region_port_de\": 12000,
  
  \"show_region_us\": true,
  \"region_install_us\": \"\",
  \"region_server_us\": \"uslogin.wizard101.com\",
  \"region_port_us\": 12000,
  
  \"show_region_fr\": false,
  \"region_install_fr\": \"\",
  \"region_server_fr\": \"login-fr.eu.wizard101.com\",
  \"region_port_fr\": 12000,
  
  \"show_region_it\": false,
  \"region_install_it\": \"\",
  \"region_server_it\": \"login-it.eu.wizard101.com\",
  \"region_port_it\": 12000,
  
  \"show_region_gb\": false,
  \"region_install_gb\": \"\",
  \"region_server_gb\": \"login-gb.eu.wizard101.com\",
  \"region_port_gb\": 12000,
  
  \"show_region_pl\": false,
  \"region_install_pl\": \"\",
  \"region_server_pl\": \"login-pl.eu.wizard101.com\",
  \"region_port_pl\": 12000,
  
  \"show_region_es\": false,
  \"region_install_es\": \"\",
  \"region_server_es\": \"login-es.eu.wizard101.com\",
  \"region_port_es\": 12000,
  
  \"show_region_gr\": false,
  \"region_install_gr\": \"\",
  \"region_server_gr\": \"login-gr.eu.wizard101.com\",
  \"region_port_gr\": 12000,
  
  \"login_wait_seconds\": 5.0,
  \"foreground_on_login\": true,
  \"set_window_title\": true,
  \"window_title_template\": \"{name} ({username})\",
  
  \"log_level\": \"INFO\",
  \"ui_theme\": \"WizDark\",
  \"account_sort_last_used\": true,
  \"account_search\": \"\"
}
`

---

##  Security Notes

- **config.json** is **NOT encrypted** and human-readable
  - Contains region settings, UI state, and preferences
  - Safe to backup and share
  - **Does NOT contain passwords**

- **data/accounts.enc.json** is **ENCRYPTED**
  - Contains account credentials and playtime data
  - Protected by AES-256 encryption with your master password
  - **Never share without master password**

---

##  Environment Variables

| Variable | Purpose |
|----------|---------|
| \WIZ_INSTALL_OVERRIDE\ | Override launcher's auto-detected Wizard101 install path |

**Example:**
`ash
set WIZ_INSTALL_OVERRIDE=C:\Games\Wizard101
.\\venv\\Scripts\\python.exe main.py
`

---

##  Customizing Settings

### Via UI
1. Go to **Settings** tab
2. Modify desired settings
3. Click **Save Settings** button
4. Changes persist to \config.json\

### Via config.json (Manual Edit)
1. Stop the launcher
2. Edit \config.json\ with any text editor
3. Start the launcher - changes load automatically

### Region-Specific Settings
Region settings can be customized:
1. Click on region tab (e.g., US, FR)
2. Edit **Install Path**, **Server**, **Port**
3. Click **Set as Current** to activate (or just change settings without switching)
4. Changes auto-save to \config.json\

---

##  Getting Default Values

To restore default settings for a region:
1. Go to that region's tab
2. Click ** Reset to Default** button
3. Server and port reset to factory values
4. Custom install path cleared

---

##  Common Configuration Tasks

### Use Different Install Path for a Region
1. Go to region tab (e.g., FR)
2. Set **Install Path** to your custom directory
3. Click **Set as Current** (or just leave the tab)
4. Next launch of that region uses this path

### Change Default Login Server
1. Go to region tab
2. Modify **Server** field
3. Click **Set as Current** to confirm
4. New server used for future logins

### Hide Regions You Don't Use
1. Go to **Settings** tab
2. Uncheck regions you don't need (e.g., FR, IT, ES)
3. Click **Save Settings**
4. Tabs instantly disappear (no restart needed!)

### Change Window Behavior
1. Go to **Settings** tab
2. Modify:
   - **Window Title Template** (e.g., \"{name} - {username}\")
   - Check/uncheck **Foreground on Login** and **Set Window Title**
3. Click **Save Settings**
4. Changes apply to next login

---

##  Troubleshooting Configuration

**Settings not saving?**
- Check that \config.json\ is writable (not read-only)
- Verify you clicked **Save Settings** button
- Check logs in **Logs** tab for errors

**Region settings reverting?**
- May indicate \config.json\ is read-only
- Or that you're using wrong region code
- Verify region code in \config.json\ matches REGION_META in \config.py\

**Wrong server being used?**
- Check that \egion_server_<code>\ matches active region
- Verify \current_region\ value in \config.json\
- Check **Logs** tab to see which region launched

**Custom install path not working?**
- Path must be valid and accessible
- Ensure \egion_install_<code>\ points to Wizard101 root directory
- Try leaving blank to use auto-detection instead
- Check Launcher.log for path resolution errors
