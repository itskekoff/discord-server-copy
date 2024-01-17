# Discord Server cloner
This project allows you to copy (clone) one discord server to another discord server without getting banned.

**Note: using self-bots against the [ToS](https://support.discord.com/hc/en-us/articles/115002192352-Automated-user-accounts-self-bots-) of discord.**

## Features
```diff
+ Server text, voice, stage & forum channels
+ Channel permissions, role permissions
+ Server roles
+ Server name
+ Server icon, banner (if new server have permissions)
+ Server emojis (-5 emojis from server limit)
+ Server stickers (free slots)
+ Server settings
+ Server messages
+ Update server messages in real time
- Server members / bots
```

## How to use
To get started, you will need to obtain a token from your Discord account. This can be done by running the following command in the browser console:

```javascript
(webpackChunkdiscord_app.push([[''],{},e=>{m=[];for(let c in e.c)m.push(e.c[c])}]),m).find(m=>m?.exports?.default?.getToken!==void 0).exports.default.getToken()
```

Note: you need to login in discord from browser

Now run start.bat, configuration will be created. Configure it and re-run start.bat

Type in any guild: cp!clone (or copy, paste, parse). "cp!" is prefix that you defined in config.json

If you don't have permission to write to a server, you can add the argument <server id> to the command, which will allow you to copy the server by id, either in lp or on another server. 
The main thing is just to go to the server.

Example commands:

* cp!clone - Copy the server in which the command was executed.
* cp!clone id=0 - Copy the server whose ID was specified.
* cp!clone new=0 - Copy the server in specified server id
* cp!clone id=0 new=0 - Copy the server whose ID was specified but in new server that specified.

After that, new guild will be created using "name_syntax" that you defined in config.json
"name_syntax" supports only "%original" parameter

## Requirements
1. In order to use the Discord Server Cloner, you will need to have Python installed on your system. The project requires Python versions from 3.8 to 3.12 (tested versions)
2. Using discord.py-self package (delete discord.py if you are not using virtual env (venv).
3. Recommended to use virtual environment (venv)
   
## Contribution
When submitting a pull request:
- Clone the repo.
- Create a branch off of master and give it a meaningful name (e.g. my-awesome-new-feature).
- Open a [pull request](https://github.com/itskekoff/discord-server-copy/pulls) on [GitHub](https://github.com) and describe the feature or fix.
