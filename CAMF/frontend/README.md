# CAMF Frontend Setup

## Prerequisites

1. **Node.js** (v16 or higher)
2. **Rust** (for Tauri)
   - Install from: https://rustup.rs/
3. **Python** (for backend)

## Directory Structure

Place all the created files in the following structure:

```
CAMF/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TitleBar.jsx
│   │   │   ├── ProjectCard.jsx
│   │   │   └── modals/
│   │   │       ├── ModalBase.jsx
│   │   │       ├── NewProjectModal.jsx
│   │   │       ├── RenameModal.jsx
│   │   │       ├── ConfirmModal.jsx
│   │   │       └── ManagePluginsModal.jsx
│   │   ├── pages/
│   │   │   ├── HomePage.jsx
│   │   │   ├── ScenesPage.jsx
│   │   │   ├── TakesPage.jsx
│   │   │   └── TakeMonitoringPage.jsx
│   │   ├── utils/
│   │   │   └── api.js
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── src-tauri/
│   │   ├── src/
│   │   │   └── main.rs
│   │   ├── build.rs
│   │   ├── Cargo.toml
│   │   └── tauri.conf.json
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── README.md
└── start.py
```

## Setup Instructions

1. **Navigate to frontend directory:**
   ```bash
   cd CAMF/frontend
   ```

2. **Install npm dependencies:**
   ```bash
   npm install
   ```

3. **Install Tauri CLI (if not already installed):**
   ```bash
   npm install --save-dev @tauri-apps/cli
   ```

## Running the Application

### Option 1: Full Stack (Recommended)

From the root directory, run:
```bash
python start.py
```

This will:
- Start the backend API server
- Start the Tauri frontend application
- Open the desktop app window

### Option 2: Frontend Only (for development)

From the `CAMF/frontend` directory:
```bash
npm run tauri dev
```

Note: The backend must be running separately for full functionality.

### Option 3: Backend Only

From the root directory:
```bash
python -m CAMF.launcher
```

## Development Commands

- `npm run dev` - Start Vite dev server only
- `npm run build` - Build the frontend
- `npm run tauri dev` - Start Tauri in development mode
- `npm run tauri build` - Build the Tauri application

## Troubleshooting

1. **Tauri build errors**: Make sure Rust is installed and updated
   ```bash
   rustup update
   ```

2. **Missing dependencies**: Try removing node_modules and reinstalling
   ```bash
   rm -rf node_modules package-lock.json
   npm install
   ```

3. **Backend connection issues**: Ensure the backend is running on `http://127.0.0.1:8000`

## Next Steps

The basic UI structure is now in place. The following pages need to be fully implemented:

1. **ScenesPage**: Complete implementation with scene list and management
2. **TakesPage**: Implement angle/take hierarchy display
3. **TakeMonitoringPage**: Full capture and monitoring interface

Each page currently has a placeholder implementation that demonstrates navigation.