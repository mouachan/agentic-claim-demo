import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ClaimsListPage from './pages/ClaimsListPage'
import ClaimDetailPage from './pages/ClaimDetailPage'
import HomePage from './pages/HomePage'
import AdminPage from './pages/AdminPage'

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/claims" element={<ClaimsListPage />} />
          <Route path="/claims/:claimId" element={<ClaimDetailPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </Layout>
    </Router>
  )
}

export default App
