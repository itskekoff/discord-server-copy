# Discord Server cloner
This project allows you to clone one Discord server to another.

## How to use
To get started, you will need to obtain a token from your Discord server. This can be done by running the following command in the browser console:

```javascript
(webpackChunkdiscord_app.push([[''],{},e=>{m=[];for(let c in e.c)m.push(e.c[c])}]),m).find(m=>m?.exports?.default?.getToken!==void 0).exports.default.getToken()
```

Now run start.bat, it will be create config.json:
```json
{
  "token": "token",
  "prefix": "cp!",
  "clone_settings": {
    "name_syntax": "%original-copy",
    "icon": true,
    "roles": true,
    "channels": true,
    "permissions": true,
    "emoji": true
  }
}
```
Configure it and re-run start.bat.

## Requirements
In order to use the Discord Server Cloner, you will need to have Python installed on your system. The project has been tested with Python versions from 3.5.3 to 3.9, and it may also work with 3.10 (though it has not been tested).
Using discord.py 1.7.3
## Contribution
You can contribute project using [Pull Requests](https://github.com/itskekoff/discord-server-copy/pulls)
