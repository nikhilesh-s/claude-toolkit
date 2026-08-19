-- GSwitch: Dock control panel for the ChatGPT Google Workspace connector.
-- Shows server/funnel state and offers start, stop, restart, copy-URL, doctor, log.

on gsPath()
	set home to POSIX path of (path to home folder)
	set candidates to {home & ".local/bin/gswitch", home & "claude-toolkit/apps/gswitch/gswitch"}
	repeat with c in candidates
		try
			do shell script "test -x " & quoted form of (c as text)
			return (c as text)
		end try
	end repeat
	error "gswitch script not found"
end gsPath

on gs(argString)
	try
		return do shell script quoted form of gsPath() & " " & argString & " 2>&1"
	on error errMsg
		return errMsg
	end try
end gs

on run
	try
		set gsBin to gsPath()
	on error
		display alert "GSwitch" message "Can't find the gswitch script. Expected it at ~/claude-toolkit/apps/gswitch/gswitch"
		return
	end try

	set stat to gs("status")
	set isUp to (stat contains "server: UP")
	if isUp then
		set headline to "Connector is running."
	else
		set headline to "Connector is stopped."
	end if

	if isUp then
		set actions to {"Copy ChatGPT connector URL", "Restart server", "Stop server", "Check setup", "Open log"}
	else
		set actions to {"Start server", "Copy ChatGPT connector URL", "Check setup", "Open log"}
	end if

	set choice to choose from list actions with title "GSwitch" with prompt headline & return & return & stat default items {}
	if choice is false then return
	set picked to item 1 of choice

	if picked is "Start server" then
		display notification "Starting…" with title "GSwitch"
		set out to gs("start")
		display notification out with title "GSwitch"
	else if picked is "Stop server" then
		gs("stop")
		display notification "Connector stopped" with title "GSwitch"
	else if picked is "Restart server" then
		display notification "Restarting…" with title "GSwitch"
		set out to gs("restart")
		display notification out with title "GSwitch"
	else if picked is "Copy ChatGPT connector URL" then
		set out to gs("url")
		set theURL to paragraph 1 of out
		set the clipboard to theURL
		display dialog "Copied to clipboard:" & return & return & theURL buttons {"OK"} default button "OK" with title "GSwitch"
	else if picked is "Check setup" then
		set out to gs("doctor")
		display dialog out buttons {"OK"} default button "OK" with title "GSwitch — setup check"
	else if picked is "Open log" then
		do shell script "open -a Console " & quoted form of ((POSIX path of (path to home folder)) & ".gswitch/gswitch.log")
	end if
end run
