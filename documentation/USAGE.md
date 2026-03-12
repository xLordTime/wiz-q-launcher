# Usage Guide

##  Quick Start

1. **Start the launcher**
   \\\ash
   python main.py
   \\\

2. **Master Password** (first run)
   - Create a strong master password to encrypt account data
   - Store it safely - it cannot be recovered if lost

3. **Add Accounts**
   - Go to **Accounts** tab
   - Click **Add** to create new account entry
   - Enter account name, Wizard101 username, and password
   - Password is encrypted and stored securely

4. **Launch Game**
   - Go to **Launch** tab
   - Current region shown at the top (e.g.,  Region: DEUTSCHLAND)
   - Choose launch method (see below)

---

##  Launch Methods

### **Quicklaunch** (Fastest)
- Launches a single instance immediately
- Uses current region settings
- No login automation
- **Use for**: Manual login or testing

\\\
Button: Quicklaunch

Wizard101 starts with current region settings
\\\

### **Start N** (Multi-Instance)
- Launch multiple instances at once
- Set instance count (1-8)
- No login automation
- Useful for multi-boxing without auto-login

\\\
Set Count: 5
Button: Start N

5 instances start with current region settings
\\\

### **Start + Auto Login** (Full Automation)
- *Requires: wizwalker package*
- Launches instances with automatic credential injection
- Starts playtime tracking automatically
- Sessions tracked until instance closes

\\\
1. Select accounts from list
2. Set instance count
3. Button: Start + Auto Login
   
   Instances start with credentials auto-injected
   
   Playtime tracking begins
\\\

---

##  Region Management

### **View Regions**
- Each enabled region has its own tab
- Visible regions controlled in **Settings** tab
- Current region shown in Launch tab (e.g.,  Region: DEUTSCHLAND)

### **Switch Region**
1. Click on desired region tab (DE, US, FR, IT, GB, PL, ES, GR)
2. (Optional) Customize:
   - **Install Path** - Custom installation directory (if not using default)
   - **Server** - Login server (pre-filled with region default)
   - **Port** - Game port (usually 12000)
3. Click ** Set as Current** button
4. Launcher switches immediately
5. Next launch will use this region

### **Reset Region to Default**
1. On any region tab
2. Click ** Reset to Default** button (red)
3. Server and port restored to factory settings
4. Custom install path cleared

### **Show/Hide Regions**
1. Go to **Settings** tab
2. Check/uncheck region visibility (8 options):
   - Deutschland (DE)  enabled by default
   - United States (US)  enabled by default
   - France (FR), Italia (IT), United Kingdom (GB), Polska (PL), España (ES), ????da (GR) - disabled by default
3. Click **Save Settings**
4. Tabs appear/disappear immediately (no restart!)

---

##  Account Management

### **Add Account**
1. Go to **Accounts** tab
2. Click **Add** button
3. Enter:
   - **Account Name** - Display name (e.g., \"Main Wizard\")
   - **Username** - Wizard101 login username
   - **Password** - Wizard101 password
4. Click Save
5. Account added to encrypted storage

### **Edit Account**
1. Go to **Accounts** tab
2. Select account from list
3. Click **Edit** button
4. Modify any field
5. Click Save

### **Delete Account**
1. Go to **Accounts** tab
2. Select account from list
3. Click **Delete** button
4. Confirm deletion
5. Account removed (playtime data kept)

### **Using in Auto-Login**
1. Go to **Launch** tab
2. Find list of accounts below launch buttons
3. Click to select accounts (multi-select available)
4. Set instance count
5. Click **Start + Auto Login**
6. Each account logs in to a separate instance

---

##  Playtime Tracking

### **Automatic Tracking**
- Enabled only with **\"Start + Auto Login\"** feature
- Tracks all selected accounts automatically
- Sessions measured from login to instance close
- Data saved to encrypted accounts.enc.json

### **View Statistics**
1. Go to **Stats** tab
2. Table shows for each account:
   - **Account** - Account name
   - **Total Playtime** - Cumulative time (e.g., \"12h 30m\")
   - **Sessions** - Number of play sessions
   - **Avg Session** - Average session duration

### **Export Statistics**
1. Go to **Stats** tab
2. Click ** Export Stats** button
3. Creates \playtime_stats.txt\ in launcher folder
4. Contains formatted playtime report for all accounts
5. File includes: Account name, username, playtime, session count, average

### **Reset Statistics**
1. Go to **Stats** tab
2. Click ** Reset All Stats** button
3. Confirm (\"Reset ALL playtime stats? This cannot be undone!\")
4. All playtime data cleared for all accounts
5. Account names and credentials preserved

---

##  Settings

### **Global Settings** (Settings tab)

| Setting | Purpose | Default |
|---------|---------|---------|
| Login Wait Seconds | Max time to wait for instance to be ready | 5 |
| Window Title Template | Format for window titles (use {name}, {username}) | \"{name} ({username})\" |
| Log Level | Logging verbosity (DEBUG, INFO, WARNING, ERROR) | INFO |
| Region Visibility | Show/hide region tabs (8 checkboxes) | DE, US enabled |

### **Per-Region Settings** (Region tabs)

| Setting | Purpose |
|---------|---------|
| Install Path | Custom Wizard101 directory (auto-detected if empty) |
| Login Server | Region's login server address |
| Port | Connection port (typically 12000) |

### **Save Settings**
- Local changes only saved after clicking **\"Save Settings\"** button
- Settings persisted in \config.json\
- Region visibility changes trigger window rebuild

---

##  Logs

### **View Logs**
1. Go to **Logs** tab
2. Click **\"Open log folder\"** button
3. Opens \logs/\ directory in file explorer
4. \launcher.log\ contains application events

### **Log Details**
- Format: Timestamp | Level | Message
- Auto-rotating by size (5 MB per file)
- Multiple backup files kept: launcher.log.1, launcher.log.2, etc.
- Verbosity controlled by **Log Level** setting

### **Common Log Messages**
- \Account login started\ - Auto-login began
- \Tracking playtime for {account}\ - Session tracking active
- \Session ended for {account}\ - Instance closed, playtime recorded
- \Region switched to {code}\ - Region change completed
- \Stats exported to playtime_stats.txt\ - Export successful

---

##  Security

### **Master Password**
- Protects all encrypted account data
- Prompted on launcher start
- AES-256 encryption for passwords
- Not stored anywhere - only salt for verification

### **Account Storage**
- File: \data/accounts.enc.json\
- All credentials encrypted
- Protected by master password
- Do not share or transfer without password

### **Config Storage**
- File: \config.json\
- Human-readable (NOT encrypted)
- Contains settings, region data, UI state
- Safe to backup and transfer

---

##  Troubleshooting

### **Auto-login not working**
1. Ensure \wizwalker\ is installed: \pip install git+https://github.com/Lapridox/wizwalker.git@2cab70d98c41ad53aef1d38e3caf3be208eeea1c\
2. Check logs in **Logs** tab
3. Verify credentials correct in **Accounts** tab
4. Try **Quicklaunch** first to verify game runs

### **Playtime not tracking**
1. Playtime only tracks with **\"Start + Auto Login\"**
2. Check that instances launched through launcher (not directly)
3. Don't force-close instances - close normally
4. Check **Stats** tab to view data

### **Region not switching**
1. Ensure region tab exists (check **Settings** tab visibility toggles)
2. Click **\"Set as Current\"** button (not just switching tabs)
3. Check if config.json is writable
4. Restart launcher if still not working

### **Master password forgotten**
1. Delete \data/accounts.enc.json\ file
2. Restart launcher
3. Create new master password
4. Re-add accounts
5. **Note**: Previous playtime data will be lost

### **Stats showing zero**
1. Playtime only records with **\"Start + Auto Login\"** feature
2. Close instances normally (don't force-kill)
3. Check **Logs** tab for tracking errors
4. Verify accounts saved properly in **Accounts** tab

---

##  FAQ

**Can I use multiple regions at once?**
Yes! Launch instances for different regions by switching regions and launching separately.

**Are my passwords safe?**
Yes! Passwords are AES-256 encrypted with your master password. They're never stored unencrypted.

**Can I export my accounts?**
Accounts are encrypted in \data/accounts.enc.json\. To backup, keep this file and remember your master password.

**Does playtime track offline?**
No, playtime only tracks instances launched through the launcher with auto-login.

**Can I reset just one account's stats?**
Currently, stats reset all at once. Individual reset coming in future version.

**What if the launcher crashes?**
Your account data and config are saved to disk. Launcher will recover them on restart.


