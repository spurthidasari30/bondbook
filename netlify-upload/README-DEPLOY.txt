BondBook Netlify upload folder

Before uploading this folder to Netlify, deploy backend/ to Render using render.yaml.
Then edit bondbook-config.js in THIS folder and set:
window.BONDBOOK_API_URL = \"https://your-render-service.onrender.com\";

Set the backend Render environment variable CORS_ORIGINS to your Netlify site URL, for example:
https://your-bondbook.netlify.app

After that, drag the contents of this netlify-upload folder into Netlify Deploys.
Do not upload backend, database, or uploads to Netlify: they require the Render persistent disk.
