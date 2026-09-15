const admin = require('firebase-admin');
const fs = require('fs');

let isFirebaseInitialized = false;

function initializeFirebase() {
  const serviceAccountPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;
  const projectId = process.env.FIREBASE_PROJECT_ID;
  const clientEmail = process.env.FIREBASE_CLIENT_EMAIL;
  const privateKey = process.env.FIREBASE_PRIVATE_KEY
    ? process.env.FIREBASE_PRIVATE_KEY.replace(/\\n/g, '\n')
    : undefined;

  try {
    if (serviceAccountPath && fs.existsSync(serviceAccountPath)) {
      const serviceAccount = JSON.parse(fs.readFileSync(serviceAccountPath, 'utf8'));
      admin.initializeApp({
        credential: admin.credential.cert(serviceAccount),
      });
      isFirebaseInitialized = true;
      console.log('[Firebase Admin] Initialized with service account file');
    } else if (projectId && clientEmail && privateKey) {
      admin.initializeApp({
        credential: admin.credential.cert({
          projectId,
          clientEmail,
          privateKey,
        }),
      });
      isFirebaseInitialized = true;
      console.log('[Firebase Admin] Initialized with environment credentials');
    } else {
      console.log('[Firebase Admin] Credentials not configured. Operating in simulated notification/event mode.');
    }
  } catch (err) {
    console.warn('[Firebase Admin] Initialization error:', err.message);
  }
}

/**
 * Triggers notification / event on user creation
 */
async function triggerUserCreatedEvent(user) {
  const eventPayload = {
    eventType: 'USER_CREATED',
    timestamp: new Date().toISOString(),
    clientId: user.client_id,
    userId: user._id ? user._id.toString() : user.id,
    email: user.email,
    name: user.name,
    role: user.role,
  };

  console.log('[Firebase Admin Event] Triggered USER_CREATED:', eventPayload);

  if (isFirebaseInitialized) {
    try {
      // Send notification message to tenant topic
      const topic = `tenant_${user.client_id.replace(/[^a-zA-Z0-9-_.~%]/g, '_')}`;
      await admin.messaging().send({
        topic,
        notification: {
          title: 'New User Registered',
          body: `User ${user.name} (${user.email}) was added.`,
        },
        data: {
          eventType: 'USER_CREATED',
          userId: eventPayload.userId,
        },
      });
      console.log(`[Firebase Admin] Notification broadcast to topic: ${topic}`);
    } catch (err) {
      console.warn('[Firebase Admin] Failed to broadcast FCM message:', err.message);
    }
  }

  return eventPayload;
}

/**
 * Triggers notification / event on user deletion
 */
async function triggerUserDeletedEvent(user) {
  const eventPayload = {
    eventType: 'USER_DELETED',
    timestamp: new Date().toISOString(),
    clientId: user.client_id,
    userId: user._id ? user._id.toString() : user.id,
    email: user.email,
    name: user.name,
  };

  console.log('[Firebase Admin Event] Triggered USER_DELETED:', eventPayload);

  if (isFirebaseInitialized) {
    try {
      const topic = `tenant_${user.client_id.replace(/[^a-zA-Z0-9-_.~%]/g, '_')}`;
      await admin.messaging().send({
        topic,
        notification: {
          title: 'User Deactivated',
          body: `User ${user.name} (${user.email}) was deactivated.`,
        },
        data: {
          eventType: 'USER_DELETED',
          userId: eventPayload.userId,
        },
      });
      console.log(`[Firebase Admin] Deletion notification broadcast to topic: ${topic}`);
    } catch (err) {
      console.warn('[Firebase Admin] Failed to broadcast FCM message:', err.message);
    }
  }

  return eventPayload;
}

module.exports = {
  initializeFirebase,
  triggerUserCreatedEvent,
  triggerUserDeletedEvent,
  admin,
  get isInitialized() {
    return isFirebaseInitialized;
  },
};
