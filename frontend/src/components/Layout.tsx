import { Link, useLocation } from 'react-router-dom'
import { ReactNode } from 'react'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()

  const isActive = (path: string) => {
    return location.pathname === path ? 'bg-blue-700' : ''
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-blue-600 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <div className="flex-shrink-0 flex items-center">
                <h1 className="text-2xl font-bold">Claims Processing Demo</h1>
              </div>
              <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                <Link
                  to="/"
                  className={`${isActive('/')} inline-flex items-center px-4 py-2 text-sm font-medium rounded-md hover:bg-blue-700 transition-colors`}
                >
                  Dashboard
                </Link>
                <Link
                  to="/claims"
                  className={`${isActive('/claims')} inline-flex items-center px-4 py-2 text-sm font-medium rounded-md hover:bg-blue-700 transition-colors`}
                >
                  Claims
                </Link>
                <Link
                  to="/admin"
                  className={`${isActive('/admin')} inline-flex items-center px-4 py-2 text-sm font-medium rounded-md hover:bg-blue-700 transition-colors`}
                >
                  ⚙️ Admin
                </Link>
              </div>
            </div>
            <div className="flex items-center">
              <span className="text-sm text-blue-100">Agentic Claims System</span>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          <p className="text-center text-sm text-gray-500">
            Claims Processing Demo - Powered by LlamaStack, MCP Agents & OpenShift AI
          </p>
        </div>
      </footer>
    </div>
  )
}
