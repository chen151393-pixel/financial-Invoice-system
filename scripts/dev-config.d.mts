export function readDevConfig(
  root: string,
  environment?: Record<string, string | undefined>,
): { apiPort: number; webPort: number; origin: string; apiTarget: string };
