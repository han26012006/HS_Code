import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const here = path.dirname(fileURLToPath(import.meta.url));
export default defineConfig({root:here,base:'/',build:{outDir:path.resolve(here,'../web_dist'),emptyOutDir:true},server:{host:'0.0.0.0'}});
