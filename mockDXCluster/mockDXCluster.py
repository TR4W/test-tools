#!/usr/bin/env python3
"""mockDXCluster - a DX cluster simulator for amateur radio.

Listens on a TCP port and emulates an AK1A-style DX cluster node: connected
telnet clients receive a continuous stream of synthetic "DX spots". Useful for
exercising logging/contest software (e.g. TR4W) against a cluster feed without a
live internet connection to a real node.

Configuration is read from ~/.config/mockDXCluster.ini (see the bundled
mockDXCluster.ini.sample). Any missing file or key falls back to the built-in
defaults below.

Standard library only; no third-party dependencies.
"""

import configparser
import random
import select
import socket
import string
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "mockDXCluster.ini"

# Built-in defaults. Used verbatim when the INI file or an individual key is
# absent, so the simulator runs with zero configuration.
DEFAULTS = {
   "port": 2323,
   "own_call": "NY4I-4",      # callsign used as the spotted station in "own" mode
   "own_spots": False,        # start emitting own-station spots instead of random
   "own_frequency": "14043.2",
   "interval_ms": 25,         # delay between successive spots, per client
}

# CW sub-band edges (kHz) that random spot frequencies are drawn from.
BAND_LIMITS = [
   (1810.0, 1840.0),    # 160m
   (3500.0, 3560.0),    # 80m
   (7000.0, 7040.0),    # 40m
   (14000.0, 14050.0),  # 20m
   (21000.0, 21050.0),  # 15m
   (28000.0, 28060.0),  # 10m
]


def load_config(path=CONFIG_PATH):
   """Return a settings dict, layering an optional INI file over DEFAULTS.

   The INI is expected to have a single [mockDXCluster] section. Unknown keys
   are ignored; malformed values fall back to the default for that key so a bad
   edit degrades gracefully rather than crashing the server.
   """
   settings = dict(DEFAULTS)

   parser = configparser.ConfigParser()
   if not parser.read(path):
      return settings

   if not parser.has_section("mockDXCluster"):
      return settings

   section = parser["mockDXCluster"]
   try:
      settings["port"] = section.getint("port", fallback=settings["port"])
      settings["interval_ms"] = section.getint("interval_ms", fallback=settings["interval_ms"])
      settings["own_spots"] = section.getboolean("own_spots", fallback=settings["own_spots"])
   except ValueError:
      # A non-numeric/non-boolean value: keep defaults for the numeric/bool keys.
      pass

   settings["own_call"] = section.get("own_call", fallback=settings["own_call"]).strip()
   settings["own_frequency"] = section.get("own_frequency", fallback=settings["own_frequency"]).strip()

   return settings


class MockDXCluster:
   """A telnet DX-cluster simulator serving any number of concurrent clients."""

   def __init__(self, settings):
      self.port = settings["port"]
      self.own_call = settings["own_call"]
      self.own_frequency = settings["own_frequency"]
      self.interval = settings["interval_ms"] / 1000.0

      # own_spots is shared across every client thread (the original behaviour:
      # the "own"/"notown" commands flip the feed for all connected clients).
      # Guard it with a lock so reads/writes from different threads are safe.
      self._own_spots = settings["own_spots"]
      self._own_lock = threading.Lock()

      # One shared RNG. The C# original constructed a fresh time-seeded Random
      # on every call, which can repeat values in tight loops; a single shared
      # instance avoids that.
      self._rng = random.Random()

      self._listener = None
      self._running = False
      self._started_at = None

   # -- shared state -------------------------------------------------------

   @property
   def own_spots(self):
      with self._own_lock:
         return self._own_spots

   @own_spots.setter
   def own_spots(self, value):
      with self._own_lock:
         self._own_spots = value

   # -- spot generation ----------------------------------------------------

   def _random_call(self):
      prefix = "".join(self._rng.choice(string.ascii_uppercase) for _ in range(2))
      number = str(self._rng.randint(0, 9))
      suffix = "".join(self._rng.choice(string.ascii_uppercase) for _ in range(3))
      return f"{prefix}{number}{suffix}"

   def _random_frequency(self):
      low, high = self._rng.choice(BAND_LIMITS)
      return f"{self._rng.uniform(low, high):.1f}"

   def _random_spot(self):
      """Build one fixed-width AK1A spot line.

      The column alignment matches real cluster output; do not "tidy" the
      field widths. Reference lines (74 columns):

      DX de W3OA-#:     7031.5  W8KJP        CW 12 dB 22 WPM CQ           ? 1945Z
      DX de NN5ABC-#: 14065.00  SM8NIO       CW                             1844Z
      """
      if self.own_spots:
         spotted = self.own_call
         spotter = self._random_call() + "-#"
         frequency = self.own_frequency
      else:
         spotted = self._random_call()
         spotter = self._random_call() + "-#"
         frequency = self._random_frequency()

      comment = f"CW {self._rng.randint(11, 36)} dB {self._rng.randint(28, 44)} WPM CQ"
      stamp = datetime.now(timezone.utc).strftime("%H%MZ")

      return f"DX de {spotter + ':':<10} {frequency:>7}  {spotted:<12} {comment:<30} {stamp}\r\n"

   # -- command handling ---------------------------------------------------

   def _process_command(self, command):
      parts = command.split()
      if not parts:
         return "Type 'help' for available commands"

      cmd = parts[0].lower()

      if cmd == "help":
         return (
            "Available commands:\r\n"
            "  help           - Show this help message\r\n"
            "  time           - Show current server time\r\n"
            "  echo <message> - Echo back your message\r\n"
            "  uptime         - Show server uptime\r\n"
            "  own            - Produce own spots\r\n"
            "  notown         - Produce random spots\r\n"
            "  bye            - Disconnect from server"
         )

      if cmd == "time":
         return f"Current server time: {datetime.now():%Y-%m-%d %H:%M:%S}"

      if cmd == "uptime":
         elapsed = time.monotonic() - self._started_at
         days, rem = divmod(int(elapsed), 86400)
         hours, rem = divmod(rem, 3600)
         minutes, seconds = divmod(rem, 60)
         return f"Server uptime: {days}d {hours}h {minutes}m {seconds}s"

      if cmd == "own":
         self.own_spots = True
         return "Producing own spots"

      if cmd == "notown":
         self.own_spots = False
         return "Producing random spots"

      if cmd == "echo":
         if len(parts) > 1:
            return "Echo: " + " ".join(parts[1:])
         return "Echo: (no message provided)"

      return f"Unknown command: '{command}'. Type 'help' for available commands."

   # -- networking ---------------------------------------------------------

   @staticmethod
   def _send(conn, message):
      conn.sendall(message.encode("ascii", errors="replace"))

   @staticmethod
   def _send_telnet_negotiation(conn):
      # WILL ECHO, WILL SUPPRESS-GO-AHEAD: keeps line-mode telnet clients happy.
      conn.sendall(bytes([0xFF, 0xFB, 0x01]))
      conn.sendall(bytes([0xFF, 0xFB, 0x03]))

   @staticmethod
   def _clean_telnet_input(data):
      """Strip telnet IAC sequences and non-printables from a recv() buffer."""
      cleaned = []
      i = 0
      length = len(data)
      while i < length:
         byte = data[i]
         if byte == 0xFF and i + 2 < length:
            i += 3  # skip IAC + command + option
            continue
         if 32 <= byte <= 126 or byte in (9, 13, 10):
            cleaned.append(byte)
         i += 1
      return bytes(cleaned).decode("ascii", errors="ignore").strip()

   def _handle_client(self, conn, addr):
      print(f"Client connected from: {addr}")
      try:
         time.sleep(0.5)
         self._send_telnet_negotiation(conn)

         self._send(conn, "Welcome to mockDXCluster!\r\n")
         self._send(conn, "Available commands: help, time, echo <message>, bye\r\n")
         self._send(conn, "> ")

         time.sleep(1.0)

         while self._running:
            time.sleep(self.interval)
            self._send(conn, self._random_spot())

            # Read client input only when something is waiting, so the spot
            # stream is never blocked on the socket.
            ready, _, _ = select.select([conn], [], [], 0)
            if not ready:
               continue

            data = conn.recv(1024)
            if not data:
               break  # client disconnected

            user_input = self._clean_telnet_input(data)
            if not user_input:
               self._send(conn, "> ")
               continue

            print(f"Received: {user_input}")

            if user_input.lower() == "bye":
               self._send(conn, "Goodbye!\r\n")
               break

            response = self._process_command(user_input)
            self._send(conn, response + "\r\n> ")
      except OSError as exc:
         print(f"Client error: {exc}")
      finally:
         print(f"Client disconnected: {addr}")
         conn.close()

   def start(self):
      self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      self._listener.bind(("", self.port))
      self._listener.listen()
      self._running = True
      self._started_at = time.monotonic()

      print(f"mockDXCluster server started on port {self.port}")
      print("Press Ctrl+C to stop the server")

      try:
         while self._running:
            try:
               conn, addr = self._listener.accept()
            except OSError as exc:
               if self._running:
                  print(f"Error accepting client: {exc}")
               break
            thread = threading.Thread(
               target=self._handle_client, args=(conn, addr), daemon=True
            )
            thread.start()
      finally:
         self.stop()

   def stop(self):
      if not self._running:
         return
      self._running = False
      if self._listener is not None:
         self._listener.close()
      print("Server stopped.")


def main():
   settings = load_config()
   server = MockDXCluster(settings)
   try:
      server.start()
   except KeyboardInterrupt:
      server.stop()


if __name__ == "__main__":
   main()
