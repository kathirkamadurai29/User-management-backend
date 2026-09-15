const swaggerJsdoc = require('swagger-jsdoc');

const options = {
  definition: {
    openapi: '3.0.0',
    info: {
      title: 'Multi-Tenant User Management Platform API',
      version: '1.0.0',
      description:
        'Production-ready REST API for multi-tenant client onboarding, authentication, isolated user CRUD, activity logging, and AI insights.',
    },
    servers: [
      {
        url: 'http://localhost:5000/api/v1',
        description: 'Local Development Server',
      },
    ],
    components: {
      securitySchemes: {
        BearerAuth: {
          type: 'http',
          scheme: 'bearer',
          bearerFormat: 'JWT',
          description: 'Enter your JWT token obtained from POST /auth/token',
        },
      },
      schemas: {
        ErrorResponse: {
          type: 'object',
          properties: {
            error: {
              type: 'object',
              properties: {
                code: { type: 'string', example: 'VALIDATION_ERROR' },
                message: { type: 'string', example: 'Field "name" is required' },
              },
            },
          },
        },
        ClientRegistrationRequest: {
          type: 'object',
          required: ['name'],
          properties: {
            name: { type: 'string', example: 'Acme Corp' },
            email: { type: 'string', example: 'admin@acme.com' },
          },
        },
        ClientRegistrationResponse: {
          type: 'object',
          properties: {
            client_id: { type: 'string', example: 'cli_8f7b9c1d2e3f4a5b' },
            client_secret: {
              type: 'string',
              example: 'sec_7e12ab34cd56ef7890abcdef12345678',
              description: 'Save this secret. It is only returned once upon creation.',
            },
            name: { type: 'string', example: 'Acme Corp' },
            email: { type: 'string', example: 'admin@acme.com' },
            created_at: { type: 'string', example: '2026-09-14T12:00:00.000Z' },
          },
        },
        AuthTokenRequest: {
          type: 'object',
          required: ['client_id', 'client_secret'],
          properties: {
            client_id: { type: 'string', example: 'cli_8f7b9c1d2e3f4a5b' },
            client_secret: { type: 'string', example: 'sec_7e12ab34cd56ef7890abcdef12345678' },
          },
        },
        AuthTokenResponse: {
          type: 'object',
          properties: {
            access_token: { type: 'string', example: 'eyJhbGciOiJIUzI1NiIsIn...' },
            token_type: { type: 'string', example: 'Bearer' },
            expires_in: { type: 'string', example: '24h' },
            client: {
              type: 'object',
              properties: {
                client_id: { type: 'string', example: 'cli_8f7b9c1d2e3f4a5b' },
                name: { type: 'string', example: 'Acme Corp' },
              },
            },
          },
        },
        UserCreateRequest: {
          type: 'object',
          required: ['name', 'email'],
          properties: {
            name: { type: 'string', example: 'Jane Doe' },
            email: { type: 'string', example: 'jane.doe@acme.com' },
            role: { type: 'string', enum: ['admin', 'member', 'viewer'], example: 'member' },
            status: { type: 'string', enum: ['active', 'inactive', 'pending'], example: 'active' },
          },
        },
        UserUpdateRequest: {
          type: 'object',
          properties: {
            name: { type: 'string', example: 'Jane Doe' },
            role: { type: 'string', enum: ['admin', 'member', 'viewer'], example: 'admin' },
            status: { type: 'string', enum: ['active', 'inactive', 'pending'], example: 'active' },
          },
        },
        UserResponse: {
          type: 'object',
          properties: {
            _id: { type: 'string', example: '66e57a3e9c4b123456789abc' },
            client_id: { type: 'string', example: 'cli_8f7b9c1d2e3f4a5b' },
            name: { type: 'string', example: 'Jane Doe' },
            email: { type: 'string', example: 'jane.doe@acme.com' },
            role: { type: 'string', example: 'member' },
            status: { type: 'string', example: 'active' },
            is_deleted: { type: 'boolean', example: false },
            created_at: { type: 'string', example: '2026-09-14T12:00:00.000Z' },
            updated_at: { type: 'string', example: '2026-09-14T12:00:00.000Z' },
          },
        },
        ActivityResponse: {
          type: 'object',
          properties: {
            metrics: {
              type: 'object',
              properties: {
                total_requests: { type: 'integer', example: 142 },
                status_2xx: { type: 'integer', example: 135 },
                status_4xx: { type: 'integer', example: 7 },
                status_5xx: { type: 'integer', example: 0 },
                endpoints_breakdown: {
                  type: 'object',
                  additionalProperties: { type: 'integer' },
                  example: { 'GET /users': 80, 'POST /users': 25 },
                },
              },
            },
            logs: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  client_id: { type: 'string', example: 'cli_8f7b9c1d2e3f4a5b' },
                  endpoint: { type: 'string', example: '/api/v1/users' },
                  method: { type: 'string', example: 'GET' },
                  status: { type: 'integer', example: 200 },
                  timestamp: { type: 'string', example: '2026-09-14T12:15:00.000Z' },
                },
              },
            },
          },
        },
        InsightsResponse: {
          type: 'object',
          properties: {
            insight: {
              type: 'string',
              example: 'Platform activity shows healthy operational patterns with 95% successful user read operations.',
            },
            generated_at: { type: 'string', example: '2026-09-14T12:30:00.000Z' },
            sample_count: { type: 'integer', example: 50 },
          },
        },
      },
    },
    paths: {
      '/clients': {
        post: {
          summary: 'Register a new tenant client',
          tags: ['Clients & Authentication'],
          requestBody: {
            required: true,
            content: { 'application/json': { schema: { $ref: '#/components/schemas/ClientRegistrationRequest' } } },
          },
          responses: {
            201: {
              description: 'Client registered successfully',
              content: { 'application/json': { schema: { $ref: '#/components/schemas/ClientRegistrationResponse' } } },
            },
            400: { description: 'Validation error', content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } } },
          },
        },
      },
      '/auth/token': {
        post: {
          summary: 'Exchange client credentials for JWT',
          tags: ['Clients & Authentication'],
          requestBody: {
            required: true,
            content: { 'application/json': { schema: { $ref: '#/components/schemas/AuthTokenRequest' } } },
          },
          responses: {
            200: {
              description: 'Token issued successfully',
              content: { 'application/json': { schema: { $ref: '#/components/schemas/AuthTokenResponse' } } },
            },
            401: { description: 'Invalid credentials', content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } } },
          },
        },
      },
      '/users': {
        get: {
          summary: 'List all users for current tenant',
          tags: ['Users Management'],
          security: [{ BearerAuth: [] }],
          parameters: [
            { name: 'search', in: 'query', schema: { type: 'string' }, description: 'Case-insensitive search on name or email' },
            { name: 'status', in: 'query', schema: { type: 'string', enum: ['active', 'inactive', 'pending'] }, description: 'Filter by user status' },
          ],
          responses: {
            200: {
              description: 'Users list',
              content: { 'application/json': { schema: { type: 'object', properties: { users: { type: 'array', items: { $ref: '#/components/schemas/UserResponse' } }, total: { type: 'integer' } } } } },
            },
            401: { description: 'Unauthorized' },
          },
        },
        post: {
          summary: 'Create a new user scoped to tenant',
          tags: ['Users Management'],
          security: [{ BearerAuth: [] }],
          requestBody: {
            required: true,
            content: { 'application/json': { schema: { $ref: '#/components/schemas/UserCreateRequest' } } },
          },
          responses: {
            201: { description: 'User created', content: { 'application/json': { schema: { $ref: '#/components/schemas/UserResponse' } } } },
            400: { description: 'Validation error' },
            409: { description: 'User already exists' },
          },
        },
      },
      '/users/{id}': {
        get: {
          summary: 'Get single tenant user by ID',
          tags: ['Users Management'],
          security: [{ BearerAuth: [] }],
          parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
          responses: {
            200: { description: 'User details', content: { 'application/json': { schema: { $ref: '#/components/schemas/UserResponse' } } } },
            404: { description: 'User not found' },
          },
        },
        put: {
          summary: 'Update tenant user by ID',
          tags: ['Users Management'],
          security: [{ BearerAuth: [] }],
          parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
          requestBody: {
            required: true,
            content: { 'application/json': { schema: { $ref: '#/components/schemas/UserUpdateRequest' } } },
          },
          responses: {
            200: { description: 'User updated', content: { 'application/json': { schema: { $ref: '#/components/schemas/UserResponse' } } } },
            404: { description: 'User not found' },
          },
        },
        delete: {
          summary: 'Soft delete / deactivate user by ID',
          tags: ['Users Management'],
          security: [{ BearerAuth: [] }],
          parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
          responses: {
            200: { description: 'User deactivated successfully' },
            404: { description: 'User not found' },
          },
        },
      },
      '/activity': {
        get: {
          summary: 'Get usage stats and recent activity logs for tenant',
          tags: ['Activity & Usage'],
          security: [{ BearerAuth: [] }],
          responses: {
            200: { description: 'Activity metrics and logs', content: { 'application/json': { schema: { $ref: '#/components/schemas/ActivityResponse' } } } },
            401: { description: 'Unauthorized' },
          },
        },
      },
      '/insights': {
        get: {
          summary: 'Generate AI activity summary insight',
          tags: ['Activity & Usage'],
          security: [{ BearerAuth: [] }],
          responses: {
            200: { description: 'AI generated operational insight', content: { 'application/json': { schema: { $ref: '#/components/schemas/InsightsResponse' } } } },
            401: { description: 'Unauthorized' },
          },
        },
      },
    },
  },
  apis: [],
};

const swaggerSpec = swaggerJsdoc(options);

module.exports = swaggerSpec;
