================================================================================
   OpenCode Helper  -  USER GUIDE
================================================================================

WHAT IS THIS?
--------------------------------------------------------------------------------
When OpenCode goes wrong, you only ever lose your patience -- never your chats.
Your conversations are saved on the computer, and this little tool fixes what
breaks, saves copies, or restarts the app for you. You never need to worry about
"ENOENT", "database", or any of that jargon. This guide tells you exactly what
to click depending on your situation.

YOU MUST HAVE THIS FIRST:
--------------------------------------------------------------------------------
   Python installed on your computer.
   Test: open the Start menu, type "cmd", press Enter, then type:  python
   If you see "Python 3.x" you are ready. If not, download it (free) from
   https://www.python.org/downloads/  and install it (tick "Add python to PATH").

HOW TO OPEN THE TOOL:
--------------------------------------------------------------------------------
   1. Double-click the file:  opencode-repair-sessions.bat
   2. A black window opens. This is normal.
   3. It asks you what's wrong. You type a number (1, 2, 3 or 4) and press Enter.
   4. The window shows you what happened. When it says "press any key",
      press any key to close it.


NOW, WHAT IS HAPPENING TO YOU?  (find your situation)
--------------------------------------------------------------------------------

SITUATION 1  -  "My chats stopped loading / everything fails / an error flashes"
--------------------------------------------------------------------------------
WHY IT HAPPENS:
   You renamed, moved, or deleted the project folder (the one the chats were
   opened in). The chats are 100% safe -- they just lost their way home.
WHAT TO DO:
   1. Close OpenCode completely first. (All windows. The whole app.)
   2. Open this helper and type  1.
   3. It shows which chats are affected and guesses the right folder.
      Just press Enter to accept its guess, or type the number of a folder.
   4. When it finishes, open OpenCode again and open your project folder.
      Your chats are back, exactly where you left them.

SITUATION 2  -  "Nothing is wrong, but I want a safety copy before I try things"
--------------------------------------------------------------------------------
WHAT TO DO:
   1. Open this helper and type  2.
   2. It saves a copy into the "backups" folder next to the helper.
   3. Done. Keep that folder somewhere safe (and private).

SITUATION 3  -  "The assistant is unavailable/hitting limits, but I still need
                 my conversation"
--------------------------------------------------------------------------------
WHY IT HAPPENS:
   The assistant (like big-pickle) is temporarily limited. This passes with
   time on its own. You are not losing anything.
WHAT TO DO:
   1. Open this helper and type  3.
   2. Pick the chat you need (its number).
   3. Your chat is saved as a normal file in the "transcripts" folder,
      next to the helper. Open it with any text editor.
   4. Copy your last reply + your next question into a NEW chat (here or in any
      other assistant). Continue from there if you must keep working.
   5. When the limits pass, reopen the original chat and send your last
      message again - it remembers everything.

SITUATION 4  -  "OpenCode is frozen / stuck / not responding"
--------------------------------------------------------------------------------
WHAT TO DO:
   1. Open this helper and type  4.
   2. It asks if you want to close OpenCode. Type  y  and press Enter.
   3. OpenCode closes. Every chat is saved and will be there when you open the
      app again. This is the safe version of "Ctrl+Alt+Del it".

SITUATION 5  -  "I want to use this on my other laptop"
--------------------------------------------------------------------------------
WHAT TO DO:
   1. Copy this whole folder (or the .zip) to the other laptop, e.g. by USB
      or any file-sharing app.
   2. Install Python on that laptop if it isn't there (see "YOU MUST HAVE..."),
   3. Double-click the .bat and follow the same situations above.
      The tool automatically finds that laptop's own chats - no setup needed.


WHERE YOUR CHATS LIVE (for the curious)
--------------------------------------------------------------------------------
   All chats are stored in this file, and it is never deleted when you close
   tabs or quit the app:
      C:\Users\YOURNAME\.local\share\opencode\opencode.db
   Backups made by option 2 land in:  backups\
   Option 1 also saves a copy there first:  backups\before-repair-....db
   Chats saved by option 3 land in:   transcripts\
   Keep backups private - treat them like your passwords.

ONE MORE IMPORTANT RULE
--------------------------------------------------------------------------------
   For SITUATION 1 only: OpenCode must be fully closed while the helper fixes
   the chats. For situations 2, 3 and 4 the helper works even while OpenCode
   is open.
================================================================================