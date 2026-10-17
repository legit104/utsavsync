# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

## Volunteer verification and language

The login language choice is saved in the browser and follows the visitor or volunteer into the dashboard (English, Hindi or Marathi). To enable real email/password sign-in and password recovery, configure VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in the frontend environment. Without those values, visitor login remains a local demo flow.

Volunteers cannot gain access by selecting the Volunteer tile or setting a browser header. Their coordinator issues a unique, email-bound, one-use code. The backend stores only the SHA-256 hash in volunteer_access_codes, redeems it atomically, and returns an eight-hour signed token. The token signing secret and Supabase service key stay on the backend.

Setup:
1. Run hackathon_backend/supabase_schema.sql in the Supabase SQL editor.
2. Configure SUPABASE_URL, SUPABASE_SERVICE_KEY, and a random VOLUNTEER_SESSION_SECRET in hackathon_backend/.env. Keep both secrets private.
3. Create a volunteer code with cd hackathon_backend then python issue_volunteer_code.py volunteer@example.org --expires-hours 72. Share the printed code with that person privately.
4. Start the backend. Select Volunteer, sign in with the invited email, and enter the code. The pass expires and works only once.

Volunteer privileges are enforced by FastAPI on the server, including field reports, sensor updates, site closures, pickup completion, festival profile changes, simulation controls, and the reroute demo. In Supabase Auth mode, only server-controlled app_metadata.role can grant additional volunteer access; user-editable metadata is ignored.
