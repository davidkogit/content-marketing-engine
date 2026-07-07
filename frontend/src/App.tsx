import { AuthProvider } from "@/contexts/auth-context"
import AppRoutes from "@/router"

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
