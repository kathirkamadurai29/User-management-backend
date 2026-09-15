/**
 * Centralized Error Handling Middleware
 * Guarantees standard JSON error shape: { error: { code, message } }
 */
function errorHandler(err, req, res, next) {
  console.error(`[Error] ${req.method} ${req.originalUrl}:`, err);

  // Handle JSON parse errors from express.json()
  if (err instanceof SyntaxError && err.status === 400 && 'body' in err) {
    return res.status(400).json({
      error: {
        code: 'INVALID_JSON',
        message: 'Malformed JSON payload in request body.',
      },
    });
  }

  const statusCode = err.statusCode || (err.status && typeof err.status === 'number' ? err.status : 500);
  const errorCode = err.code || (statusCode === 500 ? 'INTERNAL_SERVER_ERROR' : 'REQUEST_ERROR');
  const message = err.message || 'An unexpected internal error occurred.';

  res.status(statusCode).json({
    error: {
      code: errorCode,
      message,
    },
  });
}

function notFoundHandler(req, res) {
  res.status(404).json({
    error: {
      code: 'NOT_FOUND',
      message: `The requested endpoint ${req.method} ${req.originalUrl} does not exist.`,
    },
  });
}

module.exports = {
  errorHandler,
  notFoundHandler,
};
