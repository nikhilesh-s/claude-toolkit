-- GSwitch: Dock picker that flips the active gswitch Google account.
on run
	set gsDir to (POSIX path of (path to home folder)) & ".gswitch/"
	set acctDir to gsDir & "accounts"
	try
		set acctNames to paragraphs of (do shell script "ls " & quoted form of acctDir & " | sed 's/\\.json$//'")
	on error
		display alert "GSwitch" message "No accounts yet. In Terminal run:  gswitch add"
		return
	end try
	set activeAcct to do shell script "cat " & quoted form of (gsDir & "active") & " 2>/dev/null || true"
	set menuItems to {}
	repeat with a in acctNames
		if (a as text) is activeAcct then
			set end of menuItems to "✓ " & a
		else
			set end of menuItems to (a as text)
		end if
	end repeat
	set choice to choose from list menuItems with title "GSwitch" with prompt "Active Google account for ChatGPT:" default items {}
	if choice is false then return
	set picked to item 1 of choice
	if picked starts with "✓ " then set picked to text 3 thru -1 of picked
	do shell script "printf '%s\\n' " & quoted form of picked & " > " & quoted form of (gsDir & "active")
	display notification "Active: " & picked with title "GSwitch"
end run
