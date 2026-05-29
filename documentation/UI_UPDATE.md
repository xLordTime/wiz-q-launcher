## ✅ UI Updated with Full Region Support (5.2.0)

Your Wizard101 Launcher now displays **all region information clearly** with per-region tabs!

### **Key UI Improvements**

#### **1. Launch Tab**
- 🌍 **Current Region Display** - Shows active region at the top (e.g., "🌍 Region: DEUTSCHLAND")
- Instances field + Quicklaunch / Start N / Start + Auto Login buttons
- Account selection for auto-login with region-specific credentials
- Window foreground & title template checkboxes

#### **2. Per-Region Tabs** (Visible when enabled)
- **Separate tab for each region**: DE, US, FR, IT, GB, PL, ES, GR
- **Region-specific settings**:
  - Install path (custom per-region)
  - Login Server (pre-filled with region default)
  - Port (default 12000)
- **🎮 Set as Current Button** - Switch launcher to this region with one click
- **↺ Reset to Default Button** - Restore original server/port settings (red styling)

#### **3. Settings Tab**
- **Global Settings**:
  - Login wait seconds
  - Window title template
  - Log level selector
- **Region Visibility Toggles** (8 checkboxes):
  - Deutschland (DE) ✓ enabled by default
  - United States (US) ✓ enabled by default
  - France (FR) - disabled by default
  - Italia (IT) - disabled by default
  - United Kingdom (GB) - disabled by default
  - Polska (PL) - disabled by default
  - España (ES) - disabled by default
  - Ελλάδα (GR) - disabled by default
- **Live reload**: Toggling region visibility instantly adds/removes tabs (no restart!)
- **Save Settings** button - persists all changes
- **Discord Rich Presence** section — enable, client ID, update interval, yield-to-game toggle
- **Discord Webhook Notifications** section — URL, enable, test button, session-start/end/errors toggles
- **UI Theme** — 10 themes, applies immediately; Save Window State checkbox
- **Update Checker** — check_for_updates toggle, manual check button
- **Playtime Tracking** — auto_playtime_tracking and track_without_autologin toggles
- **Launch Options** — extra_args field (space-separated arguments passed to the game)
- **Security** — Change Master Password button
- **Ctrl+S** — saves all settings without clicking the button

#### **4. Window Title**
Shows: `Wiz Q Launcher v5.2.0 | 🎮 Active: DEUTSCHLAND`

---

### **Region Data Structure**

Each region has:
- **Server**: Region-specific login server (e.g., `login-de.eu.wizard101.com`)
- **Port**: 12000 (same for all regions)
- **Install Path**: Custom install directory per region (optional)
- **Visibility Toggle**: Choose which regions to show

All region settings are **saved per-region** in config.json:
```json
{
  "current_region": "de",
  "show_region_de": true,
  "show_region_us": true,
  "region_install_de": "",
  "region_server_de": "login-de.eu.wizard101.com",
  "region_port_de": 12000,
  ...
}
```

---

### **How to Use**

1. **Launch Tab**: Shows current active region - start instances with launcher.py
2. **Switch Region**: Go to any Region tab → click "🎮 Set as Current" → window rebuilds
3. **Configure Region**: Still on Region tab → enter install path + server + port → click button
4. **Show/Hide Regions**: Settings tab → check/uncheck countries → click "Save settings"
5. **Reset**: On any Region tab → click "↺ Reset" → restores defaults

---

### **Technical Details**

- ✅ **Version**: 5.2.0
- ✅ **REGION_META**: 8 regions with metadata
- ✅ **Config Keys**: `region_install_*`, `region_server_*`, `region_port_*`
- ✅ **Live Reload**: Region visibility toggles rebuild window
- ✅ **Region Switching**: Set as Current saves & rebuilds UI
- ✅ **Per-Region Defaults**: Each region has server/port defaults

---

### **Launch Behavior**

When you click "Quicklaunch" or "Start N" or "Start + Auto Login":
1. App reads **current_region** from config
2. Looks up **region_server_{current_region}** and **region_port_{current_region}**
3. Uses **region_install_{current_region}** if set, otherwise finds Wizard101 folder
4. Launches with `-L {server} {port} -A {region}` args

**Now you can see exactly which region you're launching!** 🎮

