# Discord: sales, grind sessions and valuable pickups

Optional, off by default. Everything goes to one channel on our Discord server.

Settings → Discord → **Connect Discord** opens Discord's own page ("Companion wants to know who you
are", scope `identify`: your user ID and name only, no messages, servers or friends). Companion
hands the token once to our report server, which asks Discord who you are, drops the token, and
gives Companion a signed card. The card is all Companion keeps.

**What can be shared.** Each item has its own switch in Settings:
- **Your shop's sales:** the item, how many, the price, and the shop's total today. Also, once
  each: "your shop sold out", "your shop closed" (the game left the Free Market), and a correction
  when a sale turns out not to have happened.
- **Your grind sessions:** sessions over 10 minutes, when they end. The post has the map, the time,
  EXP/hr, EXP gained, your levels, kills, solo or party, the top three pickups and the mesos.
- **Valuable pickups:** an item you pick up worth over 80,000 mesos each (the market median).
  Items with no known price aren't shared, and at most 10 are shared a day.

**How it's kept safe:**
- The server writes every message itself, from plain fields, under your character's name.
- A message can tag only you: no @everyone, no roles, no one else, and no links.
- Posts wait in `discord_outbox.json` until the server takes them. No internet, or Discord saying
  "slow down", only delays them: nothing is lost or posted twice.
- Sales within a minute of the last message go together.
- Unlink, or the switches, stop it.
- Tip: set the channel's Notification Settings to Only @mentions.

Discord works in builds that carry `reports.json` (the report server's address). Without it,
Settings says "Not set up in this build". Players linked before this change see "Connect again"
once.

**Admin setup (once):**
1. In Discord, make the channel, for example `#companion`. Optional: Edit Channel → Permissions →
   turn off Send Messages for @everyone, so only Companion posts there (webhooks still post).
2. Edit Channel → Integrations → Webhooks → New Webhook, named Companion, with the picture
   `web/logo.png` → Copy Webhook URL. Don't paste it in chat.
3. Go to https://discord.com/developers/applications → New Application "Companion", with the logo
   (players see it on the authorize page) → OAuth2:
   - copy the Client ID;
   - Redirects → Add `http://localhost:8765/discord` → Save.

   No bot, no client secret.
4. In the Vercel project `companion-reports` → Settings → Environment Variables, add:
   - `DISCORD_WEBHOOK` (the webhook URL);
   - `DISCORD_CLIENT_ID`;
   - `CARD_SECRET` (32 or more random characters).

   Then redeploy.
5. Test: Settings → Connect Discord → Authorize. A hello tagging you arrives in the channel.

**If something goes wrong:**
- **Someone misbehaves:** add their Discord ID to `BLOCKED_IDS` (comma-separated) and redeploy.
- **Pause everything:** set `DISCORD_MODE=off`.
- **The webhook leaks:** make a new one and update `DISCORD_WEBHOOK`. No new build is needed.
- **`CARD_SECRET` leaks:** change it. Everyone then presses Connect again.
- **Limits:** one Discord ID posts at most 20 times in 10 minutes.

Connect needs the dashboard on port 8765 (the only redirect registered). If another copy of
Companion holds that port, close it first.

[Back to the README](../README.md)
