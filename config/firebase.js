const admin = require('firebase-admin');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

let isFirebaseInitialized = false;
let storageBucket = null;

function initializeFirebase() {
  const serviceAccountPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;
  const projectId = process.env.FIREBASE_PROJECT_ID;
  const clientEmail = process.env.FIREBASE_CLIENT_EMAIL;
  const privateKey = process.env.FIREBASE_PRIVATE_KEY
    ? process.env.FIREBASE_PRIVATE_KEY.replace(/\\n/g, '\n')
    : undefined;
  const bucketName = process.env.FIREBASE_STORAGE_BUCKET || (projectId ? `${projectId}.firebasestorage.app` : 'user-management-3ea6d.firebasestorage.app');

  try {
    const possiblePaths = [
      serviceAccountPath,
      serviceAccountPath ? path.resolve(__dirname, '..', serviceAccountPath) : null,
      path.resolve(__dirname, '..', 'serviceAccountKey.json'),
      path.resolve(__dirname, '..', 'ServiceAccountKey.json'),
      path.resolve(__dirname, '..', 'ServiceAccountKey.json.json'),
    ].filter(Boolean);

    const foundPath = possiblePaths.find((p) => fs.existsSync(p));

    if (foundPath) {
      const serviceAccount = JSON.parse(fs.readFileSync(foundPath, 'utf8'));
      if (!admin.apps.length) {
        admin.initializeApp({
          credential: admin.credential.cert(serviceAccount),
          storageBucket: bucketName,
        });
      }
      isFirebaseInitialized = true;
      storageBucket = admin.storage().bucket();
      console.log(`[Firebase Admin] Storage initialized via key: ${path.basename(foundPath)} (bucket: ${bucketName})`);
    } else if (projectId && clientEmail && privateKey) {
      if (!admin.apps.length) {
        admin.initializeApp({
          credential: admin.credential.cert({
            projectId,
            clientEmail,
            privateKey,
          }),
          storageBucket: bucketName,
        });
      }
      isFirebaseInitialized = true;
      storageBucket = admin.storage().bucket();
      console.log(`[Firebase Admin] Storage initialized via environment credentials (bucket: ${bucketName})`);
    } else {
      console.log('[Firebase Admin] Storage credentials not configured. Operating in simulated resilient mode.');
    }
  } catch (err) {
    console.warn('[Firebase Admin] Storage initialization notice:', err.message);
  }
}

/**
 * Uploads a user profile picture to Firebase Storage and returns its public/media URL.
 * Falls back gracefully to base64 data URI if storage bucket is offline or unconfigured.
 */
async function uploadProfilePicture(fileBuffer, filename = 'avatar.jpg', contentType = 'image/jpeg', clientId = 'default') {
  if (!fileBuffer || !fileBuffer.length) {
    return '';
  }

  const cleanClient = String(clientId).replace(/[^a-zA-Z0-9_]/g, '_');
  const safeName = path.basename(filename) || 'avatar.jpg';
  const uniqueBlobPath = `avatars/${cleanClient}/${crypto.randomBytes(8).toString('hex')}_${safeName}`;

  if (isFirebaseInitialized && storageBucket) {
    try {
      const file = storageBucket.file(uniqueBlobPath);
      await file.save(fileBuffer, {
        metadata: { contentType },
        resumable: false,
      });

      // Attempt to make public
      try {
        await file.makePublic();
        const publicUrl = `https://storage.googleapis.com/${storageBucket.name}/${uniqueBlobPath}`;
        console.log(`[Firebase Storage] Uploaded public avatar: ${publicUrl}`);
        return publicUrl;
      } catch (aclErr) {
        console.log(`[Firebase Storage] makePublic notice (${aclErr.message}), returning direct media URL.`);
      }

      const encodedPath = encodeURIComponent(uniqueBlobPath);
      const mediaUrl = `https://firebasestorage.googleapis.com/v0/b/${storageBucket.name}/o/${encodedPath}?alt=media`;
      console.log(`[Firebase Storage] Uploaded media URL: ${mediaUrl}`);
      return mediaUrl;
    } catch (uploadErr) {
      console.warn(`[Firebase Storage] Upload notice (${uploadErr.message}), using fallback.`);
    }
  }

  // Resilient fallback: base64 data URI
  const b64 = fileBuffer.toString('base64');
  return `data:${contentType};base64,${b64}`;
}

module.exports = {
  initializeFirebase,
  uploadProfilePicture,
  admin,
  get isInitialized() {
    return isFirebaseInitialized;
  },
};
