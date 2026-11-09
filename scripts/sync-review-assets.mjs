import {copyFile} from 'node:fs/promises';
await copyFile(new URL('../frontend/src/factReview.js',import.meta.url),new URL('../frontend/public/assets/fact-review.js',import.meta.url));
