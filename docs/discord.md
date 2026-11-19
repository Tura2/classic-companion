# Discord shop-sale pings

Optional, off by default.

Settings → Discord → **Connect Discord** opens Discord's own page ("Companion wants to know who you
are", scope `identify`: your user ID and name only, no messages, servers or friends). Companion
reads your ID once and drops the access token; it's never saved. After that, each sale in your shop
is posted to our server's **#shop-sales** channel, tagging only you (every message allows a mention
of your ID and nothing else: no @everyone, no roles, no one else), so your phone pings. Sent: the
item, how many, the price, your character's name and the shop's total today. Also, once each: "your
shop sold out" and "your shop closed" (the game left the Free Market). Sales wait in
`discord_outbox.json` until Discord takes them: no internet or Discord saying "slow down" delays
them, never loses or repeats them. Sales within a minute of the last message go together. Unlink
or the switch in Settings stops it. Tip: set #shop-sales → Notification Settings → Only @mentions.

The webhook and the Discord app's client ID come with the build (`discord.json` next to
`build.bat`, never committed); without it Settings says "Not set up in this build".

**Admin setup (once, about 5 minutes):**
1. Create a text channel `#shop-sales`. Optional: Edit Channel → Permissions → turn off Send
   Messages for @everyone, so it holds only sales (webhooks still post).
2. Edit Channel → Integrations → Webhooks → New Webhook, name it Companion, picture
   `web/logo.png` → Copy Webhook URL (don't paste it in chat).
3. https://discord.com/developers/applications → New Application "Companion", with the logo
   (players see it on the authorize page) → OAuth2: copy the Client ID; Redirects → Add
   `http://localhost:8765/discord` → Save. No bot, no client secret.
4. Next to `build.bat`: `discord.json` = `{"webhook": "https://discord.com/api/webhooks/...",
   "client_id": "123456789012345678"}`. Run `build.bat`, upload `dist\CompanionSetup.exe` to Releases. Keep the file name
   `CompanionSetup.exe`: the website's and README's Download links point at that name in the latest release.
5. Test: Settings → Connect Discord → Authorize; a message tagging you arrives in #shop-sales.
6. If the webhook URL leaks (it's inside a public exe, so someone determined can post to the
   channel, though never read it): delete the webhook, make a new one, update `discord.json`,
   rebuild and re-release. Players' links keep working.

Connect needs the dashboard on port 8765 (the only redirect registered): with another copy of
Companion holding that port, close it first.

[Back to the README](../README.md)
