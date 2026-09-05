let token: string | null = null;

export function setAdminToken(next: string | null): void {
  token = next;
}

export function getAdminToken(): string | null {
  return token;
}
