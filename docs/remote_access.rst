Remote access
=============

The control deck is proxied through Home Assistant, so any remote path
that reaches your Home Assistant instance reaches the panel too — no
extra printer-side plugins, VPN clients, or Moonraker changes are
required.

Recommended: Home Assistant Cloud
---------------------------------

`Nabu Casa remote access <https://www.nabucasa.com/config/remote/>`_
exposes your instance over an encrypted relay. Once enabled:

* Open the panel from the remote URL — all ``/api/moonraker/*`` routes
  (telemetry, cameras, thumbnails, actions, file metadata) work through
  the same authenticated session.
* Cameras stream through the Home Assistant proxy endpoints, so live
  video works without exposing Moonraker or the printer's web UI.
* The deck can be installed as a PWA on your phone from the remote URL
  (browser menu → *Install app* / *Add to Home Screen*).

Alternatives
------------

* A VPN (WireGuard, Tailscale) terminating on your home network —
  simplest fully-private option.
* A TLS reverse proxy in front of Home Assistant. Do **not** expose
  Moonraker's own port (7125) directly to the internet; the Home
  Assistant routes already carry everything the panel needs.

Security checklist for remote use
---------------------------------

* Keep the panel role on ``admin_only`` unless remote viewers should be
  able to control the printer; the ``operator`` role still blocks
  destructive actions (cancel, delete, e-stop is always reachable).
* Prefer Home Assistant accounts with MFA enabled for anyone who can
  reach the panel remotely.
* ``/api/moonraker/panel_*`` endpoints require a valid Home Assistant
  session except the static code assets, which carry no printer data.

Voice control
-------------

The integration ships Assist intents for print status, pause, and
resume, so any Assist surface — including voice over a remote
connection — can answer "what's the printer doing" or act on a print.
Sentences are scoped to the ``moonraker`` domain; name slots match the
printer's configured device name.
