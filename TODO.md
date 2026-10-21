# Ambience — to do

## Next up
- [ ] **Tray icon** — sync keeps running with the window closed; quick start/stop and
      all-lights-off from the tray.
- [ ] **Packaging** — PKGBUILD, `.desktop` entry and an icon, so Ambience is in the launcher.
      (Also silences the harmless "Could not register app ID … 'ambience'" warning at startup.)
- [ ] **Settings page** — bridge info + re-pair, scroll speed (now `Theme.wheelPixelsPerLine`),
      fade length (`Theme.fadeMs`), default sync intensity.

## Later — responsiveness (parked 2026-10-21: looks fine by eye; revisit if it ever feels late)
- [ ] **Measure first:** a "timing test" that flashes the screen and the lights together;
      film both with a phone in slow motion and count frames for the true end-to-end delay.
      Measured so far: our music analysis reacts 25 ms after a kick, beats are detected
      within 1 ms; the bridge → Zigbee → bulb trip is likely the largest part.
- [ ] **Screen: smarter smoothing** — react instantly to big changes (scene cuts, flashes),
      smooth only small flicker; would make Subtle/Moderate feel snappier without jitter.
- [ ] **Music: predict the beat** — lock onto the tempo and send each flash early by the
      measured bridge-to-bulb delay, so it lands *on* the beat. We hear the audio before it
      leaves the computer, which a phone listening through its microphone can't.
- [ ] **Music: quiet passages** — auto-levelling lifts a quiet background hum to full
      brightness on Intense; consider a minimum-loudness gate (seen in testing).

## Ideas
- [ ] Create a screen-shaped entertainment area from within Ambience (the API allows it),
      instead of sending people to the phone app.
- [ ] "Save current lights as a scene."
- [ ] More gallery presets; maybe let people make their own.
- [ ] Push to a private GitHub repo; decide on a licence before anything goes public.

## Done
- Milestone 1 — pairing, certificate pinning, keys in KWallet, DTLS entertainment streaming.
- Milestone 2 — Home + Room screens on live bridge state, glow design, instant scene
  preview, 700 ms colour fades.
- Milestone 3 — Scenes page, two-row strips, dynamic play + speed, own photos, gallery,
  delete scene, effect scenes, scrolling (hi-res wheels arrive as "touchpads" — decided by
  scroll phase).
- Milestone 4 — screen sync and music sync in a separate process, Sync page with live preview.
- Pairing inside the app (first run, or `AMBIENCE_PAIR=1` to re-pair), with a bridge identity
  check before any pairing request.
