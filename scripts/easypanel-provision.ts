#!/usr/bin/env node

/**
 * Easypanel Provisioning Script for Oraculo (Hermes Enterprise)
 * 
 * ⚠️ IMPORTANT: This script uses the Easypanel tRPC API, which is NOT officially documented
 * or supported. The API may change without notice in future Easypanel updates.
 * 
 * This script is intended for bootstrap/provisioning use only, not for continuous deployment.
 * If the API breaks, fallback to manual UI configuration.
 */

import crypto from "crypto";
import * as fs from "fs";
import * as path from "path";

// ============================================================================
// NOTE: .env is loaded automatically via `node -r dotenv/config` in package.json
// ============================================================================

// ============================================================================
// TYPES
// ============================================================================

interface EasypanelConfig {
  url: string;
  token: string;
  projectName: string;
}

interface ProvisionOutput {
  timestamp: string;
  projectId: string;
  postgres: {
    serviceId: string;
    password: string;
    host: string;
    port: number;
    user: string;
    database: string;
    url: string;
  };
  redis: {
    serviceId: string;
    password: string;
    host: string;
    port: number;
    url: string;
  };
  apps: {
    admin: {
      serviceId: string;
      status: string;
    };
    atendimento: {
      serviceId: string;
      status: string;
    };
  };
}

// ============================================================================
// UTILITIES
// ============================================================================

function generateSecurePassword(length: number = 32): string {
  return crypto.randomBytes(Math.ceil(length / 2)).toString("hex").slice(0, length);
}

function maskToken(token: string): string {
  if (token.length < 10) return "***";
  return token.slice(0, 4) + "..." + token.slice(-4);
}

function log(message: string): void {
  console.log(`[${new Date().toISOString()}] ${message}`);
}

function logError(message: string): void {
  console.error(`[ERROR] ${message}`);
}

function logDebug(message: string): void {
  if (process.env.DEBUG_EASYPANEL) {
    console.log(`[DEBUG] ${message}`);
  }
}

async function trpcCall(
  config: EasypanelConfig,
  procedure: string,
  input: Record<string, unknown>
): Promise<unknown> {
  const url = `${config.url}/api/trpc/${procedure}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${config.token}`,
  };

  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ json: input }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`tRPC error (${response.status}): ${errorText}`);
    }

    const data = await response.json() as unknown;
    logDebug(`Response from ${procedure}: ${JSON.stringify(data).slice(0, 200)}`);
    
    // Handle different response formats from tRPC API
    // Format 1: { result: { data: ... } }
    if (
      typeof data === "object" &&
      data !== null &&
      "result" in data &&
      typeof (data as Record<string, unknown>).result === "object" &&
      (data as Record<string, unknown>).result !== null &&
      "data" in ((data as Record<string, unknown>).result as Record<string, unknown>)
    ) {
      const result = ((data as Record<string, unknown>).result as Record<string, unknown>).data;
      logDebug(`Returning nested data from ${procedure}`);
      return result;
    }
    
    // Format 2: Direct response (for some endpoints)
    if (typeof data === "object" && data !== null) {
      logDebug(`Returning direct response from ${procedure}`);
      return data;
    }
    
    // Fallback
    logDebug(`Returning raw response from ${procedure}`);
    return data;
  } catch (error) {
    throw new Error(
      `tRPC call failed: ${procedure}. Details: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

// ============================================================================
// PROVISIONING FUNCTIONS
// ============================================================================

async function ensureProject(config: EasypanelConfig): Promise<string> {
  log(`Checking if project '${config.projectName}' exists...`);

  try {
    const response = await trpcCall(config, "projects.listProjects", {}) as unknown;
    
    // Handle different response formats
    let projects: Array<{ id?: string; name: string }> = [];
    
    if (Array.isArray(response)) {
      projects = response;
    } else if (
      typeof response === "object" &&
      response !== null &&
      "json" in response &&
      Array.isArray((response as Record<string, unknown>).json)
    ) {
      projects = (response as Record<string, unknown>).json as Array<{ id?: string; name: string }>;
    }
    
    const existing = projects.find((p) => p.name === config.projectName);

    if (existing) {
      const projectId = existing.id || config.projectName; // Fallback to name if no ID
      log(`✓ Project '${config.projectName}' already exists (ID: ${projectId})`);
      return projectId;
    }
  } catch (error) {
    log(`Warning: Could not list projects. Attempting to create new one. Details: ${error instanceof Error ? error.message : String(error)}`);
  }

  log(`Creating project '${config.projectName}'...`);
  const project = await trpcCall(config, "projects.createProject", {
    name: config.projectName,
    description: "Oraculo (Hermes Enterprise) - Auto-provisioned via script",
  }) as { id: string };

  log(`✓ Project created (ID: ${project.id})`);
  return project.id;
}

async function ensurePostgres(
  config: EasypanelConfig,
  projectId: string
): Promise<{ serviceId: string; password: string; host: string }> {
  log("Creating PostgreSQL service...");

  const password = generateSecurePassword();
  log(`Generating secure password: ${maskToken(password)}`);

  try {
    const postgres = await trpcCall(config, "services.postgres.createService", {
      projectName: config.projectName,
      serviceName: "postgres",
      password,
      rootUser: "postgres",
      databaseName: "hermes",
      version: "16",
    }) as { id: string };

    log(`✓ PostgreSQL created (ID: ${postgres.id})`);
    return {
      serviceId: postgres.id,
      password,
      host: `${config.projectName}_postgres`,
    };
  } catch (error) {
    if (error instanceof Error && error.message.includes("already exists")) {
      log(`✓ PostgreSQL service already exists`);
      return {
        serviceId: "postgres",
        password: "",
        host: `${config.projectName}_postgres`,
      };
    }
    throw error;
  }
}

async function ensureRedis(
  config: EasypanelConfig,
  projectId: string
): Promise<{ serviceId: string; password: string; host: string }> {
  log("Creating Redis service...");

  const password = generateSecurePassword();
  log(`Generating secure password: ${maskToken(password)}`);

  try {
    const redis = await trpcCall(config, "services.redis.createService", {
      projectName: config.projectName,
      serviceName: "redis",
      password,
      version: "7",
    }) as { id: string };

    log(`✓ Redis created (ID: ${redis.id})`);
    return {
      serviceId: redis.id,
      password,
      host: `${config.projectName}_redis`,
    };
  } catch (error) {
    if (error instanceof Error && error.message.includes("already exists")) {
      log(`✓ Redis service already exists`);
      return {
        serviceId: "redis",
        password: "",
        host: `${config.projectName}_redis`,
      };
    }
    throw error;
  }
}

async function ensureApp(
  config: EasypanelConfig,
  projectId: string,
  appName: "hermes-admin" | "hermes-atendimento",
  postgresPassword: string,
  redisPassword: string,
  postgresHost: string,
  redisHost: string
): Promise<string> {
  log(`Creating app '${appName}'...`);

  const environment: Record<string, string> = {
    NODE_ENV: "production",
    HERMES_PG_HOST: postgresHost,
    HERMES_PG_PORT: "5432",
    HERMES_PG_USER: "hermes",
    HERMES_PG_PASSWORD: postgresPassword,
    HERMES_PG_DATABASE: "hermes",
    HERMES_REDIS_HOST: redisHost,
    HERMES_REDIS_PORT: "6379",
    HERMES_REDIS_PASSWORD: redisPassword,
    // Profile-specific config
    ...(appName === "hermes-admin" && {
      HERMES_PROFILE: "admin",
      HERMES_ADMIN_MODE: "true",
    }),
    ...(appName === "hermes-atendimento" && {
      HERMES_PROFILE: "atendimento",
    }),
  };

  // 1. Create app service
  let serviceId = "";
  
  try {
    const appResponse = await trpcCall(config, "services.app.createService", {
      projectName: config.projectName,
      serviceName: appName,
    }) as unknown;
    
    logDebug(`App response: ${JSON.stringify(appResponse)}`);
    
    // Extract service ID from response (could be nested)
    if (typeof appResponse === "object" && appResponse !== null) {
      if ("id" in appResponse) {
        serviceId = (appResponse as Record<string, unknown>).id as string;
      } else if ("serviceId" in appResponse) {
        serviceId = (appResponse as Record<string, unknown>).serviceId as string;
      } else if ("_id" in appResponse) {
        serviceId = (appResponse as Record<string, unknown>)._id as string;
      } else {
        // Fallback: use serviceName as ID
        serviceId = appName;
      }
    }
    
    log(`✓ App service created (ID: ${serviceId})`);
  } catch (error) {
    if (error instanceof Error && error.message.includes("already exists")) {
      log(`✓ App '${appName}' already exists`);
      serviceId = appName;
    } else {
      throw error;
    }
  }

  // 2. Set source image
  log(`Setting Docker image...`);
  await trpcCall(config, "services.app.updateSourceImage", {
    projectName: config.projectName,
    serviceName: appName,
    image: "ghcr.io/m4rrec0s/oraculo/hermes-enterprise:latest",
  });
  log(`✓ Docker image set`);

  // 3. TODO: Set environment variables
  // Note: Endpoint name unknown. Will need to be discovered via API inspection
  // try {
  //   log(`Setting environment variables...`);
  //   await trpcCall(config, "services.app.setEnvironment", {
  //     projectName: config.projectName,
  //     serviceName: appName,
  //     env: Object.entries(environment).map(([key, value]) => ({ key, value })),
  //   });
  //   log(`✓ Environment variables set`);
  // } catch (error) {
  //   log(`Warning: Could not set environment variables: ${error instanceof Error ? error.message : String(error)}`);
  // }

  // 4. TODO: Deploy service
  // Note: Endpoint name unknown. Will need to be discovered via API inspection
  // log(`Deploying service...`);
  // await trpcCall(config, "services.app.deploy", {
  //   projectName: config.projectName,
  //   serviceName: appName,
  // });
  // log(`✓ App '${appName}' deployed`);

  log(`✓ App '${appName}' configured (ID: ${serviceId})`);
  log(`Note: To complete deployment, set environment variables and deploy via Easypanel UI`);

  return serviceId;
}

// ============================================================================
// MAIN
// ============================================================================

async function main(): Promise<void> {
  // Validate environment variables
  const easypanelUrl = process.env.EASYPANEL_URL;
  const easypanelToken = process.env.EASYPANEL_TOKEN;

  if (!easypanelUrl) {
    logError("EASYPANEL_URL environment variable is not set");
    process.exit(1);
  }

  if (!easypanelToken) {
    logError("EASYPANEL_TOKEN environment variable is not set");
    logError("To generate a token, see README.md for setup instructions");
    process.exit(1);
  }

  const projectName = process.env.EASYPANEL_PROJECT_NAME || "oraculo";

  const config: EasypanelConfig = {
    url: easypanelUrl,
    token: easypanelToken,
    projectName,
  };

  log("=".repeat(70));
  log("Easypanel Provisioning: Oraculo (Hermes Enterprise)");
  log("=".repeat(70));
  log(`URL: ${config.url}`);
  log(`Token: ${maskToken(config.token)}`);
  log(`Project: ${config.projectName}`);
  log("");

  const output: ProvisionOutput = {
    timestamp: new Date().toISOString(),
    projectId: "",
    postgres: {
      serviceId: "",
      password: "",
      host: "",
      port: 5432,
      user: "hermes",
      database: "hermes",
      url: "",
    },
    redis: {
      serviceId: "",
      password: "",
      host: "",
      port: 6379,
      url: "",
    },
    apps: {
      admin: {
        serviceId: "",
        status: "pending",
      },
      atendimento: {
        serviceId: "",
        status: "pending",
      },
    },
  };

  try {
    // Step 1: Ensure project
    log("STEP 1/5: Provisioning project");
    output.projectId = await ensureProject(config);
    log("✓ Project provisioned");
    log("");

    // Step 2: Ensure PostgreSQL
    log("STEP 2/5: Provisioning PostgreSQL");
    const pgResult = await ensurePostgres(config, output.projectId);
    output.postgres.serviceId = pgResult.serviceId;
    output.postgres.password = pgResult.password;
    output.postgres.host = pgResult.host;
    output.postgres.url = `postgresql://hermes:${pgResult.password}@${pgResult.host}:5432/hermes`;
    log("✓ PostgreSQL provisioned");
    log("");

    // Step 3: Ensure Redis
    log("STEP 3/5: Provisioning Redis");
    const redisResult = await ensureRedis(config, output.projectId);
    output.redis.serviceId = redisResult.serviceId;
    output.redis.password = redisResult.password;
    output.redis.host = redisResult.host;
    output.redis.url = `redis://:${redisResult.password}@${redisResult.host}:6379`;
    log("✓ Redis provisioned");
    log("");

    // Step 4: Ensure hermes-admin app
    log("STEP 4/5: Provisioning hermes-admin app");
    output.apps.admin.serviceId = await ensureApp(
      config,
      output.projectId,
      "hermes-admin",
      output.postgres.password,
      output.redis.password,
      output.postgres.host,
      output.redis.host
    );
    output.apps.admin.status = "provisioned";
    log("✓ hermes-admin app provisioned");
    log("");

    // Step 5: Ensure hermes-atendimento app
    log("STEP 5/5: Provisioning hermes-atendimento app");
    output.apps.atendimento.serviceId = await ensureApp(
      config,
      output.projectId,
      "hermes-atendimento",
      output.postgres.password,
      output.redis.password,
      output.postgres.host,
      output.redis.host
    );
    output.apps.atendimento.status = "provisioned";
    log("✓ hermes-atendimento app provisioned");
    log("");

    // Save output
    log("Saving provisioning output...");
    const outputPath = path.join(process.cwd(), ".easypanel-provision-output.json");
    fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));
    log(`✓ Output saved to ${outputPath}`);
    log("");

    // Summary
    log("=".repeat(70));
    log("✓ PROVISIONING COMPLETE");
    log("=".repeat(70));
    log("");
    log("Project Details:");
    log(`  Project ID: ${output.projectId}`);
    log(`  Project Name: ${projectName}`);
    log("");
    log("PostgreSQL Details:");
    log(`  Service ID: ${output.postgres.serviceId}`);
    log(`  Host (internal): ${output.postgres.host}`);
    log(`  Port: ${output.postgres.port}`);
    log(`  User: ${output.postgres.user}`);
    log(`  Database: ${output.postgres.database}`);
    if (output.postgres.password) {
      log(`  Password: ${maskToken(output.postgres.password)} (saved in output file)`);
    }
    log("");
    log("Redis Details:");
    log(`  Service ID: ${output.redis.serviceId}`);
    log(`  Host (internal): ${output.redis.host}`);
    log(`  Port: ${output.redis.port}`);
    if (output.redis.password) {
      log(`  Password: ${maskToken(output.redis.password)} (saved in output file)`);
    }
    log("");
    log("Apps:");
    log(`  hermes-admin: ${output.apps.admin.serviceId} (${output.apps.admin.status})`);
    log(`  hermes-atendimento: ${output.apps.atendimento.serviceId} (${output.apps.atendimento.status})`);
    log("");
    log("All credentials saved in: .easypanel-provision-output.json");
    log("⚠️  Keep this file safe — it contains sensitive information!");
    log("");
  } catch (error) {
    logError("");
    logError("=".repeat(70));
    logError("PROVISIONING FAILED");
    logError("=".repeat(70));
    logError(`Error: ${error instanceof Error ? error.message : String(error)}`);
    logError("");
    logError("Troubleshooting:");
    logError("  1. Verify EASYPANEL_URL and EASYPANEL_TOKEN are correct");
    logError("  2. Check network connectivity to Easypanel");
    logError("  3. Ensure your API token has sufficient permissions");
    logError("  4. For API token generation, see README.md");
    logError("");
    process.exit(1);
  }
}

main();
